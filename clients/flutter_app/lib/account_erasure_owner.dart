import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'account_erasure_adapter.dart';
import 'account_erasure_client.dart';
import 'account_erasure_flow.dart';
import 'account_erasure_local_cleanup.dart';
import 'account_erasure_provider.dart';
import 'account_erasure_status.dart';
import 'integration.dart';

/// Explicit, default-unused composition for one receipt owner in this isolate.
/// Production composition must inject its SecureStore and original SessionController;
/// construction performs no storage, provider, transport, or business login work.
/// Only an explicit start/resume opens a vault. The captured root entry opens its
/// flow page; the controller alone owns its disposal (no direct root-flow injection).
///
/// The persisted pointer contains an opaque UUID/provider, never Person/subject,
/// login tokens or a receipt secret. It is not account ownership proof. A new
/// login cannot adopt it: resume requires explicit confirmation and a definitively
/// signed-out original session. Resume cannot create a request. No existing record,
/// receipt or unknown marker is overwritten/deleted on open, failure or disposal.
/// Cross-process/keychain concurrency is not provided by DurableStore; the root
/// must use one composition/isolate and a trusted installation-local store.
class AccountErasureOwner {
  AccountErasureOwner({
    required DurableStore store,
    required SessionController session,
    required ApiTransport transport,
    required bool Function() isOnline,
    required Listenable connectivity,
    AppleLoginPort? apple,
    LineLoginPort? line,
    SecureIds? ids,
  })  : _store = store,
        _session = session,
        _transport = transport,
        _isOnline = isOnline,
        _connectivity = connectivity,
        _apple = apple,
        _line = line,
        _ids = ids ?? SecureIds(),
        _sessionGeneration = session.generation {
    _cleanup = _OwnerCleanup(this, SessionBoundErasureCleanup(session));
    _session.generationChanges.addListener(_sessionChanged);
  }

  static const _ownerKey = 'erasure-owner:v1';
  static AccountErasureOwner? _lease;
  final DurableStore _store;
  final SessionController _session;
  final ApiTransport _transport;
  final bool Function() _isOnline;
  final Listenable _connectivity;
  final AppleLoginPort? _apple;
  final LineLoginPort? _line;
  final SecureIds _ids;
  late final _OwnerCleanup _cleanup;
  int _sessionGeneration;
  int? _permittedCleanupGeneration;
  bool _active = true;
  bool _opening = false;
  int _pendingCalls = 0;
  ErasureReceiptVault? _vault;
  AccountErasureAdapter? _adapter;
  _OwnedFlow? _flow;

  AccountErasureFlowPort? get flow => _active ? _flow : null;

  void requireCurrent() {
    if (!_active || _session.generation != _sessionGeneration) {
      dispose();
      throw const ErasureReceiptUnavailable();
    }
  }

  void _sessionChanged() {
    if (!_active) return;
    final generation = _session.generation;
    if (_permittedCleanupGeneration == generation) {
      // Consume only the synchronous clear performed by our captured cleanup.
      // A reentrant/later login increments again and must invalidate this owner.
      _permittedCleanupGeneration = null;
      _sessionGeneration = generation;
      return;
    }
    if (generation != _sessionGeneration) dispose();
  }

  void _requireProvider(String provider) {
    if (!((provider == 'apple' && _apple != null) ||
        (provider == 'line' && _line != null))) {
      // GoogleLoginPort has no nonce contract. Never fall back to normal login.
      throw const ErasureReceiptUnavailable();
    }
  }

  ErasureFreshProvider _provider(String name) {
    _requireProvider(name);
    if (name == 'apple') {
      return AppleErasureFreshProvider(_apple!,
          requireCurrent: requireCurrent, isOnline: _isOnline);
    }
    return LineErasureFreshProvider(_line!,
        requireCurrent: requireCurrent, isOnline: _isOnline);
  }

  Future<AccountErasureFlowPort> start(
      {required String provider, required bool confirmed}) async {
    requireCurrent();
    if (!confirmed) throw const ErasureReceiptUnavailable();
    _requireProvider(provider);
    return _open(provider);
  }

  Future<AccountErasureFlowPort> resume({required bool confirmed}) async {
    requireCurrent();
    if (!confirmed) throw const ErasureReceiptUnavailable();
    return _open(null);
  }

  String _newScope() {
    // Reuse the existing secure entropy source; format its first 128 bits as v4.
    final bytes = base64Url.decode(base64Url.normalize(_ids.next()));
    if (bytes.length != 32) throw const ErasureReceiptUnavailable();
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex =
        bytes.take(16).map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  (String, String) _record(String? raw) {
    if (raw == null || raw.length > 512) {
      throw const ErasureReceiptUnavailable();
    }
    final value = jsonDecode(raw);
    if (value is! Map<String, dynamic> ||
        value.length != 3 ||
        !value.keys.toSet().containsAll({'version', 'scope', 'provider'}) ||
        value['version'] is! int ||
        value['version'] != 1 ||
        !AccountErasureStatus.validId(value['scope']) ||
        value['provider'] is! String) {
      throw const ErasureReceiptUnavailable();
    }
    _requireProvider(value['provider'] as String);
    return (value['scope'] as String, value['provider'] as String);
  }

  Future<AccountErasureFlowPort> _open(String? newProvider) async {
    if (_opening || _adapter != null || _lease != null) {
      throw const ErasureReceiptUnavailable();
    }
    // Reserve before the first await, also against a second controller instance.
    _lease = this;
    _opening = true;
    AccountErasureAdapter? candidate;
    try {
      requireCurrent();
      if (newProvider == null) {
        if (_session.accessToken != null) {
          throw const ErasureReceiptUnavailable();
        }
        final present = await _session.observePresence();
        requireCurrent();
        if (present != false || _session.accessToken != null) {
          throw const ErasureReceiptUnavailable();
        }
      }
      final existing = await _store.read(_ownerKey);
      requireCurrent();
      late final String scope;
      late final String provider;
      if (newProvider == null) {
        (scope, provider) = _record(existing);
      } else {
        if (existing != null) throw const ErasureReceiptUnavailable();
        scope = _newScope();
        provider = newProvider;
        final occupied = await _store
            .countKeysWithPrefix('erasure-receipt:v1:$scope', maximum: 0);
        requireCurrent();
        if (occupied != 0) throw const ErasureReceiptUnavailable();
        final encoded =
            jsonEncode({'version': 1, 'scope': scope, 'provider': provider});
        await _store.write(_ownerKey, encoded);
        requireCurrent();
        final saved = await _store.read(_ownerKey);
        requireCurrent();
        if (saved != encoded) throw const ErasureReceiptUnavailable();
      }
      final vault = ErasureReceiptVault.forTesting(_store, scope);
      _vault = vault;
      candidate = await AccountErasureAdapter.open(
        vault: vault,
        transport: _transport,
        provider: _provider(provider),
        isOnline: () => _active && _isOnline(),
        connectivity: _connectivity,
        requestAllowed: newProvider != null,
        freshRecoveryAllowed: true,
        localCleanup: _cleanup,
      );
      requireCurrent();
      _adapter = candidate;
      _flow = _OwnedFlow(this, candidate);
      candidate = null;
      return _flow!;
    } on Object {
      candidate?.dispose();
      _closeResources();
      throw const ErasureReceiptUnavailable();
    } finally {
      _opening = false;
      if (!_active || _adapter == null) _releaseLease();
    }
  }

  void _releaseLease() {
    if (_opening || _pendingCalls != 0 || (_active && _adapter != null)) {
      return;
    }
    if (identical(_lease, this)) _lease = null;
  }

  Future<T> _call<T>(Future<T> Function() operation) async {
    requireCurrent();
    _pendingCalls++;
    try {
      final result = await operation();
      requireCurrent();
      return result;
    } finally {
      _pendingCalls--;
      _releaseLease();
    }
  }

  void _closeResources() {
    final adapter = _adapter;
    final vault = _vault;
    _adapter = null;
    _flow = null;
    _vault = null;
    adapter?.dispose();
    vault?.dispose();
  }

  /// Invalidates pending/native/page operations without erasing durable evidence.
  /// In-flight opens/actions retain the process lease until every await settles.
  /// Invalidation cannot cancel an already-started storage write. No new vault
  /// may race that write, even after the old page has been cleared synchronously.
  void dispose() {
    if (!_active) return;
    _active = false;
    _session.generationChanges.removeListener(_sessionChanged);
    _closeResources();
    if (!_opening) _releaseLease();
  }
}

/// Lifetime accounting only; the accepted adapter still owns action semantics.
class _OwnedFlow
    implements AccountErasureFlowPort, AccountErasureFreshRecoveryPort {
  _OwnedFlow(this._owner, this._adapter);
  final AccountErasureOwner _owner;
  final AccountErasureAdapter _adapter;

  @override
  Listenable get changes => _adapter.changes;
  @override
  bool get online => _adapter.online;
  @override
  int get generation => _adapter.generation;
  @override
  bool get canRequest => _adapter.canRequest;
  @override
  bool get outcomeUnknown => _adapter.outcomeUnknown;
  @override
  String? get jobId => _adapter.jobId;
  @override
  bool get canRecoverWithProof => _adapter.canRecoverWithProof;

  @override
  void requireCurrent() {
    _owner.requireCurrent();
    _adapter.requireCurrent();
  }

  @override
  Future<Map<String, dynamic>?> readStatus() =>
      _owner._call(_adapter.readStatus);
  @override
  Future<void> request({required bool confirmed}) =>
      _owner._call(() => _adapter.request(confirmed: confirmed));
  @override
  Future<void> verify({required bool confirmed}) =>
      _owner._call(() => _adapter.verify(confirmed: confirmed));
  @override
  Future<void> cancel({required bool confirmed}) =>
      _owner._call(() => _adapter.cancel(confirmed: confirmed));
  @override
  Future<void> recoverReceipt({required bool confirmed}) =>
      _owner._call(() => _adapter.recoverReceipt(confirmed: confirmed));
  @override
  Future<void> recoverWithProof({required bool confirmed}) =>
      _owner._call(() => _adapter.recoverWithProof(confirmed: confirmed));
}

class _OwnerCleanup implements ErasureLocalCleanup {
  _OwnerCleanup(this._owner, this._cleanup);
  final AccountErasureOwner _owner;
  final SessionBoundErasureCleanup _cleanup;

  @override
  void requireCurrent() {
    _owner.requireCurrent();
    _cleanup.requireCurrent();
  }

  @override
  Future<void> clearBeforeVerification() {
    requireCurrent();
    _owner._permittedCleanupGeneration = _owner._sessionGeneration + 1;
    try {
      // The existing helper increments synchronously before returning a Future.
      // Do not leave this exemption open while awaiting storage/purge/provider I/O.
      return _cleanup.clearBeforeVerification();
    } finally {
      _owner._permittedCleanupGeneration = null;
    }
  }
}
