import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'account_erasure_status.dart';
import 'integration.dart';

class ErasureReceiptUnavailable implements Exception {
  const ErasureReceiptUnavailable();
}

/// Not a login credential. Never serialize to logs or attach to request URLs.
class ErasureReceipt {
  const ErasureReceipt._(this.id, this._secret, this.requestedAt,
      [this.expiresAt]);
  final String id;
  final String _secret;
  final DateTime requestedAt;
  final DateTime? expiresAt;
  // Only the distinct six-field recovery contract supplies this persisted field;
  // ordinary successful request receipts keep their original four-field format.
  bool get recoveredByProof => expiresAt != null;

  static ErasureReceipt _recovered(Map<String, dynamic> value, DateTime now) {
    if (value.length != 6 ||
        !value.keys.toSet().containsAll({
          'id',
          'status',
          'receipt_secret',
          'requested_at',
          'updated_at',
          'receipt_expires_at'
        }) ||
        !{'requested', 'verified', 'processing', 'needs_attention'}
            .contains(value['status'])) {
      throw const ErasureReceiptUnavailable();
    }
    final status = AccountErasureStatus.parse({
      'id': value['id'],
      'status': value['status'],
      'requested_at': value['requested_at'],
      'updated_at': value['updated_at'],
    });
    final expiry = _expiry(value['receipt_expires_at']);
    if (!expiry.isAfter(now.toUtc()) || !expiry.isAfter(status.updatedAt)) {
      throw const ErasureReceiptUnavailable();
    }
    final receipt = parse({
      'id': value['id'],
      'status': 'requested',
      'receipt_secret': value['receipt_secret'],
      'requested_at': value['requested_at']
    });
    return ErasureReceipt._(
        receipt.id, receipt._secret, receipt.requestedAt, expiry);
  }

  static DateTime _expiry(Object? value) {
    if (value is! String ||
        value.length > 32 ||
        !RegExp(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|\+00:00)$')
            .hasMatch(value)) {
      throw const ErasureReceiptUnavailable();
    }
    final parsed = DateTime.tryParse(value);
    if (parsed == null ||
        !parsed.isUtc ||
        parsed.toIso8601String().substring(0, 19) != value.substring(0, 19)) {
      throw const ErasureReceiptUnavailable();
    }
    return parsed.toUtc();
  }

  static ErasureReceipt _restore(Map<String, dynamic> value) {
    if (!value.containsKey('receipt_expires_at')) return parse(value);
    final fields = Map<String, dynamic>.from(value);
    final expiry = _expiry(fields.remove('receipt_expires_at'));
    final receipt = parse(fields);
    if (!expiry.isAfter(receipt.requestedAt)) {
      throw const ErasureReceiptUnavailable();
    }
    return ErasureReceipt._(
        receipt.id, receipt._secret, receipt.requestedAt, expiry);
  }

  static ErasureReceipt parse(Map<String, dynamic> value) {
    if (value.length != 4 ||
        !value.keys
            .toSet()
            .containsAll({'id', 'status', 'receipt_secret', 'requested_at'}) ||
        value['status'] != 'requested' ||
        value['receipt_secret'] is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{32,256}$')
            .hasMatch(value['receipt_secret'] as String)) {
      throw const ErasureReceiptUnavailable();
    }
    try {
      final status = AccountErasureStatus.parse({
        'id': value['id'],
        'status': 'requested',
        'requested_at': value['requested_at'],
        'updated_at': value['requested_at'],
      });
      return ErasureReceipt._(
          status.id, value['receipt_secret'] as String, status.requestedAt);
    } on Object {
      throw const ErasureReceiptUnavailable();
    }
  }

  Map<String, dynamic> _stored() => {
        'id': id,
        'status': 'requested',
        'receipt_secret': _secret,
        'requested_at': requestedAt.toIso8601String(),
        if (expiresAt != null)
          'receipt_expires_at': expiresAt!.toIso8601String(),
      };
}

/// A caller-owned opaque UUID scope, NOT a Person ID or a business session.
/// Composition must invalidate before changing owners and reopen only after an
/// explicit receipt-recovery decision. No enumeration or automatic login binding.
/// Session cleanup does not delete this distinct prefix; explicit forget does.
class ErasureReceiptVault extends ChangeNotifier {
  ErasureReceiptVault.forTesting(this._store, String ownerScope)
      : _key = 'erasure-receipt:v1:$ownerScope' {
    if (!AccountErasureStatus.validId(ownerScope)) {
      throw const ErasureReceiptUnavailable();
    }
  }

  factory ErasureReceiptVault.secure(String ownerScope) =>
      ErasureReceiptVault.forTesting(SecureStore(), ownerScope);

  final DurableStore _store;
  final String _key;
  Future<void> _queue = Future<void>.value();
  bool _active = true;
  int _revision = 0;
  int get revision => _revision;

  void requireCurrent([int? expectedRevision]) {
    if (!_active ||
        (expectedRevision != null && expectedRevision != _revision)) {
      throw const ErasureReceiptUnavailable();
    }
  }

  void invalidate() {
    if (!_active) return;
    _active = false;
    _revision++;
    notifyListeners();
  }

  Future<T> _serialized<T>(Future<T> Function() operation) {
    final next = _queue.then((_) async {
      requireCurrent();
      try {
        final result = await operation();
        requireCurrent();
        return result;
      } on Object {
        throw const ErasureReceiptUnavailable();
      }
    });
    _queue = next.then<void>((_) {}, onError: (Object _) {});
    return next;
  }

  Future<ErasureReceipt?> read() => _serialized(() async {
        final raw = await _store.read(_key);
        if (raw == null) return null;
        if (raw.length > 2048) throw const ErasureReceiptUnavailable();
        final value = jsonDecode(raw);
        if (value is! Map<String, dynamic>) {
          throw const ErasureReceiptUnavailable();
        }
        return ErasureReceipt._restore(value);
      });

  Future<void> _saveRecovered(ErasureReceipt receipt, int revision) =>
      _serialized(() async {
        requireCurrent(revision);
        // A competing save is never replaced, even when it has the same job ID.
        if (await _store.read(_key) != null) {
          throw const ErasureReceiptUnavailable();
        }
        requireCurrent(revision);
        await _store.write(_key, jsonEncode(receipt._stored()));
        requireCurrent(revision);
        _revision++;
        notifyListeners();
      });

  Future<void> save(ErasureReceipt receipt) {
    requireCurrent();
    _revision++;
    notifyListeners();
    return _serialized(() => _store.write(_key, jsonEncode(receipt._stored())));
  }

  Future<void> forget() {
    requireCurrent();
    _revision++;
    notifyListeners();
    return _serialized(() => _store.delete(_key));
  }

  // Composition owns exactly one active vault per owner. This queue serializes
  // attempts in that vault; the marker also survives process/page recreation.
  // Never clear markers when forgetting a receipt or clearing a login session.
  String _attemptKey(String jobId, ErasureReceiptAction action) {
    if (!AccountErasureStatus.validId(jobId)) {
      throw const ErasureReceiptUnavailable();
    }
    return '$_key:attempt:$jobId:${action.name}';
  }

  Future<bool> actionWasSubmitted(String jobId, ErasureReceiptAction action) =>
      _serialized(
          () async => await _store.read(_attemptKey(jobId, action)) != null);

  Future<void> _reserveAction(String jobId, ErasureReceiptAction action) =>
      _serialized(() async {
        final key = _attemptKey(jobId, action);
        if (await _store.read(key) != null) {
          throw const ErasureReceiptUnavailable();
        }
        // Acknowledged durable storage MUST precede the possibly committing POST.
        // Any value (including malformed/unknown) prevents another submission.
        await _store.write(key, 'submitted-or-unknown:v1');
      });

  Future<bool> requestWasSubmitted() => _serialized(
      () async => await _store.read('$_key:request-attempt') != null);

  Future<void> _reserveRequest() => _serialized(() async {
        final key = '$_key:request-attempt';
        if (await _store.read(key) != null || await _store.read(_key) != null) {
          throw const ErasureReceiptUnavailable();
        }
        await _store.write(key, 'submitted-or-unknown:v1');
      });

  @override
  void dispose() {
    invalidate();
    super.dispose();
  }
}

/// Receipt-only status POST, never an erasure/request/cancel mutation. No bearer
/// session or refresh handling; one request per manual read, no automatic retry.
class ErasureReceiptStatusClient implements AccountErasureStatusPort {
  ErasureReceiptStatusClient._(this._vault, this._receipt, this._transport,
      this._isOnline, this._connectivity, this._revision);

  static Future<ErasureReceiptStatusClient> open(
      ErasureReceiptVault vault, ApiTransport transport,
      {required bool Function() isOnline,
      required Listenable connectivity}) async {
    final revision = vault.revision;
    final receipt = await vault.read();
    vault.requireCurrent(revision);
    if (receipt == null) throw const ErasureReceiptUnavailable();
    return ErasureReceiptStatusClient._(
        vault, receipt, transport, isOnline, connectivity, revision);
  }

  final ErasureReceiptVault _vault;
  final ErasureReceipt _receipt;
  final ApiTransport _transport;
  final bool Function() _isOnline;
  final Listenable _connectivity;
  final int _revision;

  @override
  late final Listenable changes = Listenable.merge([_vault, _connectivity]);
  @override
  bool get online => _isOnline();
  @override
  String get jobId => _receipt.id;
  @override
  void requireCurrent() => _vault.requireCurrent(_revision);

  @override
  Future<Map<String, dynamic>> read() async {
    requireCurrent();
    if (!online) throw const OfflineReadOnlyException();
    try {
      final response = await _transport.send('POST', '/account-erasure/status',
          body: {'job_id': _receipt.id, 'receipt_secret': _receipt._secret});
      requireCurrent();
      if (!online || response.status != 200 || response.body == null) {
        throw const ErasureReceiptUnavailable();
      }
      final status = AccountErasureStatus.parse(response.body!);
      if (status.id != jobId) throw const ErasureReceiptUnavailable();
      return response.body!;
    } on Object {
      throw const ErasureReceiptUnavailable();
    }
  }
}

enum ErasureReceiptAction { verify, cancel }

enum ErasureActionFailureStage { beforeSubmission, outcomeUnknown }

class ErasureActionFailure implements Exception {
  const ErasureActionFailure(this.stage);
  final ErasureActionFailureStage stage;
}

/// Must perform a fresh, nonce-bound authorization. Ordinary login tokens and
/// cached assertions are not substitutes. Native composition is not enabled here.
abstract interface class ErasureFreshProvider {
  String get provider;
  Future<String> authenticate(String nonce);
}

/// Optional verification-only local obligation, bound to the original business
/// session. Receipt/proof ownership remains independent. Cancellation must never
/// call this interface, including its currentness check.
abstract interface class ErasureLocalCleanup {
  void requireCurrent();
  Future<void> clearBeforeVerification();
}

/// One explicit action attempt per instance, including failures. A failed final
/// POST is uncertain, not retry permission. Retains receipt for status recovery;
/// never logs credentials, creates sessions or restores access. Explicitly
/// injected local cleanup runs only after fresh proof and before verification.
class ErasureReceiptActionClient {
  ErasureReceiptActionClient._(this._context, this._localCleanup);
  final ErasureReceiptStatusClient _context;
  final ErasureLocalCleanup? _localCleanup;
  bool _used = false;
  ErasureActionFailureStage _failureStage =
      ErasureActionFailureStage.beforeSubmission;

  static Future<ErasureReceiptActionClient> open(
      ErasureReceiptVault vault, ApiTransport transport,
      {required bool Function() isOnline,
      required Listenable connectivity,
      ErasureLocalCleanup? localCleanup}) async {
    return ErasureReceiptActionClient._(
        await ErasureReceiptStatusClient.open(vault, transport,
            isOnline: isOnline, connectivity: connectivity),
        localCleanup);
  }

  void _current({bool verifying = false}) {
    _context.requireCurrent();
    if (!_context.online) throw const OfflineReadOnlyException();
    if (verifying) _localCleanup?.requireCurrent();
  }

  Future<void> execute(ErasureReceiptAction action,
      {required ErasureFreshProvider provider, required bool confirmed}) async {
    if (_used) {
      throw ErasureActionFailure(_failureStage);
    }
    _used = true; // Before the first await: duplicate taps cannot race.
    bool submitted = false;
    final verifying = action == ErasureReceiptAction.verify;
    final elapsed = Stopwatch()..start();
    try {
      _current();
      final providerName = provider.provider;
      if (!confirmed || !{'apple', 'google', 'line'}.contains(providerName)) {
        throw const ErasureReceiptUnavailable();
      }
      if (await _context._vault.actionWasSubmitted(_context.jobId, action)) {
        submitted = true; // A previous attempt, not permission to submit again.
        throw const ErasureReceiptUnavailable();
      }
      _current(verifying: verifying);
      final response = await _context._transport.send(
          'POST',
          verifying
              ? '/account-erasure/receipt/challenge'
              : '/account-erasure/cancel/challenge',
          body: {
            'job_id': _context.jobId,
            'receipt_secret': _context._receipt._secret,
            'provider': providerName,
          });
      _current(verifying: verifying);
      final challenge = response.body;
      if (response.status != 200 ||
          challenge == null ||
          challenge.length != 4 ||
          !challenge.keys.toSet().containsAll(
              {'challenge_credential', 'nonce', 'provider', 'expires_in'}) ||
          challenge['provider'] != providerName ||
          challenge['challenge_credential'] is! String ||
          !RegExp(r'^[A-Za-z0-9_-]{80,4096}$')
              .hasMatch(challenge['challenge_credential'] as String) ||
          challenge['nonce'] is! String ||
          !RegExp(r'^[A-Za-z0-9_-]{43}$')
              .hasMatch(challenge['nonce'] as String) ||
          challenge['expires_in'] is! int ||
          (challenge['expires_in'] as int) < 1 ||
          (challenge['expires_in'] as int) > 300) {
        throw const ErasureReceiptUnavailable();
      }
      final lifetime = Duration(seconds: challenge['expires_in'] as int);
      if (elapsed.elapsed >= lifetime) throw const ErasureReceiptUnavailable();
      final assertion =
          await provider.authenticate(challenge['nonce'] as String);
      _current(verifying: verifying);
      if (elapsed.elapsed >= lifetime ||
          assertion.isEmpty ||
          assertion.length > 16384) {
        throw const ErasureReceiptUnavailable();
      }
      if (verifying) {
        await _localCleanup?.clearBeforeVerification();
        _current(verifying: true);
        if (elapsed.elapsed >= lifetime) {
          throw const ErasureReceiptUnavailable();
        }
      }
      submitted =
          true; // Even a transport exception may follow a server commit.
      _failureStage = ErasureActionFailureStage.outcomeUnknown;
      await _context._vault._reserveAction(_context.jobId, action);
      _current(verifying: verifying);
      if (elapsed.elapsed >= lifetime) throw const ErasureReceiptUnavailable();
      final result = await _context._transport.send(
          'POST',
          verifying
              ? '/account-erasure/receipt/verify'
              : '/account-erasure/cancel',
          body: {
            'challenge_credential': challenge['challenge_credential'],
            'provider_assertion': assertion,
            'confirmed': true,
          });
      _current(verifying: verifying);
      if (result.status != 200 ||
          result.body == null ||
          result.body!.length != 2 ||
          result.body!['id'] != _context.jobId ||
          result.body!['status'] != (verifying ? 'verified' : 'cancelled')) {
        throw const ErasureReceiptUnavailable();
      }
    } on Object {
      _failureStage = submitted
          ? ErasureActionFailureStage.outcomeUnknown
          : ErasureActionFailureStage.beforeSubmission;
      throw ErasureActionFailure(_failureStage);
    } finally {
      elapsed.stop();
    }
  }
}

/// Fresh restricted intent works without a normal login session. The server
/// resolves the proven provider identity; no client-selected Person is sent.
/// One explicitly authorized owner/flow vault must be retained for recovery.
/// Receipt storage failure after a successful POST is uncertain, never a retry.
class ErasureFreshRequestClient {
  ErasureFreshRequestClient(this._vault, this._transport,
      {required bool Function() isOnline})
      : _isOnline = isOnline,
        _revision = _vault.revision;
  final ErasureReceiptVault _vault;
  final ApiTransport _transport;
  final bool Function() _isOnline;
  final int _revision;
  bool _used = false;
  ErasureActionFailureStage _stage = ErasureActionFailureStage.beforeSubmission;

  void _current() {
    _vault.requireCurrent(_revision);
    if (!_isOnline()) throw const OfflineReadOnlyException();
  }

  Future<void> request(
      {required ErasureFreshProvider provider, required bool confirmed}) async {
    if (_used) throw ErasureActionFailure(_stage);
    _used = true;
    final elapsed = Stopwatch()..start();
    try {
      _current();
      final name = provider.provider;
      if (!confirmed || !{'apple', 'google', 'line'}.contains(name)) {
        throw const ErasureReceiptUnavailable();
      }
      if (await _vault.requestWasSubmitted()) {
        _stage = ErasureActionFailureStage.outcomeUnknown;
        throw const ErasureReceiptUnavailable();
      }
      _current();
      if (await _vault.read() != null) throw const ErasureReceiptUnavailable();
      _current();
      final response = await _transport.send(
          'POST', '/account-erasure/request/challenge',
          body: {'provider': name});
      _current();
      final challenge = response.body;
      if (response.status != 200 ||
          challenge == null ||
          challenge.length != 4 ||
          !challenge.keys.toSet().containsAll(
              {'challenge_credential', 'nonce', 'provider', 'expires_in'}) ||
          challenge['provider'] != name ||
          challenge['challenge_credential'] is! String ||
          !RegExp(r'^[A-Za-z0-9_-]{80,4096}$')
              .hasMatch(challenge['challenge_credential'] as String) ||
          challenge['nonce'] is! String ||
          !RegExp(r'^[A-Za-z0-9_-]{43}$')
              .hasMatch(challenge['nonce'] as String) ||
          challenge['expires_in'] is! int ||
          (challenge['expires_in'] as int) < 1 ||
          (challenge['expires_in'] as int) > 300) {
        throw const ErasureReceiptUnavailable();
      }
      final lifetime = Duration(seconds: challenge['expires_in'] as int);
      if (elapsed.elapsed >= lifetime) throw const ErasureReceiptUnavailable();
      final assertion =
          await provider.authenticate(challenge['nonce'] as String);
      _current();
      if (assertion.isEmpty ||
          assertion.length > 16384 ||
          elapsed.elapsed >= lifetime) {
        throw const ErasureReceiptUnavailable();
      }
      _stage = ErasureActionFailureStage.outcomeUnknown;
      await _vault._reserveRequest();
      _current();
      if (elapsed.elapsed >= lifetime) throw const ErasureReceiptUnavailable();
      final result =
          await _transport.send('POST', '/account-erasure/request', body: {
        'challenge_credential': challenge['challenge_credential'],
        'provider_assertion': assertion,
        'confirmed': true,
      });
      _current();
      if (result.status != 202 || result.body == null) {
        throw const ErasureReceiptUnavailable();
      }
      final receipt = ErasureReceipt.parse(result.body!);
      // This publishes a new receipt revision. Older readers are invalidated;
      // composition must explicitly open the new context after success.
      await _vault.save(receipt);
      _vault.requireCurrent(_revision + 1);
      if (!_isOnline()) throw const OfflineReadOnlyException();
    } on Object {
      throw ErasureActionFailure(_stage);
    } finally {
      elapsed.stop();
    }
  }
}

/// Explicit fresh proof retrieves an existing receipt, never a business login or
/// mutation. One attempt per instance; no automatic retries or unknown-marker reset.
class ErasureFreshRecoveryClient {
  ErasureFreshRecoveryClient(this._vault, this._transport,
      {required bool Function() isOnline, DateTime Function()? clock})
      : _isOnline = isOnline,
        _clock = clock ?? DateTime.now,
        _revision = _vault.revision;
  final ErasureReceiptVault _vault;
  final ApiTransport _transport;
  final bool Function() _isOnline;
  final DateTime Function() _clock;
  final int _revision;
  bool _used = false;

  void _current() {
    _vault.requireCurrent(_revision);
    if (!_isOnline()) throw const ErasureReceiptUnavailable();
  }

  Future<void> recover(
      {required ErasureFreshProvider provider, required bool confirmed}) async {
    if (_used) throw const ErasureReceiptUnavailable();
    _used = true;
    final elapsed = Stopwatch()..start();
    try {
      _current();
      final name = provider.provider;
      if (!confirmed || !{'apple', 'google', 'line'}.contains(name)) {
        throw const ErasureReceiptUnavailable();
      }
      if (await _vault.read() != null) throw const ErasureReceiptUnavailable();
      _current();
      final response = await _transport.send(
          'POST', '/account-erasure/recovery/challenge',
          body: {'provider': name});
      _current();
      final challenge = response.body;
      if (response.status != 200 ||
          challenge == null ||
          challenge.length != 4 ||
          !challenge.keys.toSet().containsAll(
              {'challenge_credential', 'nonce', 'provider', 'expires_in'}) ||
          challenge['provider'] != name ||
          challenge['challenge_credential'] is! String ||
          !RegExp(r'^[A-Za-z0-9_-]{80,4096}$')
              .hasMatch(challenge['challenge_credential'] as String) ||
          challenge['nonce'] is! String ||
          !RegExp(r'^[A-Za-z0-9_-]{43}$')
              .hasMatch(challenge['nonce'] as String) ||
          challenge['expires_in'] is! int ||
          (challenge['expires_in'] as int) < 1 ||
          (challenge['expires_in'] as int) > 300) {
        throw const ErasureReceiptUnavailable();
      }
      final lifetime = Duration(seconds: challenge['expires_in'] as int);
      if (elapsed.elapsed >= lifetime) throw const ErasureReceiptUnavailable();
      final assertion =
          await provider.authenticate(challenge['nonce'] as String);
      _current();
      if (assertion.isEmpty ||
          assertion.length > 16384 ||
          elapsed.elapsed >= lifetime) {
        throw const ErasureReceiptUnavailable();
      }
      final result =
          await _transport.send('POST', '/account-erasure/recovery', body: {
        'challenge_credential': challenge['challenge_credential'],
        'provider_assertion': assertion,
        'confirmed': true,
      });
      _current();
      if (result.status != 200 || result.body == null) {
        throw const ErasureReceiptUnavailable();
      }
      final receipt = ErasureReceipt._recovered(result.body!, _clock());
      await _vault._saveRecovered(receipt, _revision);
      _vault.requireCurrent(_revision + 1);
      if (!_isOnline()) throw const ErasureReceiptUnavailable();
    } on Object {
      throw const ErasureReceiptUnavailable();
    } finally {
      elapsed.stop();
    }
  }
}
