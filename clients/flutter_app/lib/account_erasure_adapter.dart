import 'package:flutter/foundation.dart';

import 'account_erasure_client.dart';
import 'account_erasure_flow.dart';
import 'integration.dart';

/// Explicit owner-scoped composition, never a login or native provider adapter.
/// The owner must keep exactly one active vault/adapter and dispose this adapter
/// before switching owners. Opening is an explicit authorization to read that
/// scope's existing receipt. Neither disposal nor recovery deletes durable data.
class AccountErasureAdapter extends ChangeNotifier
    implements AccountErasureFlowPort, AccountErasureFreshRecoveryPort {
  AccountErasureAdapter._(
      this._vault,
      this._transport,
      this._provider,
      this._isOnline,
      this._connectivity,
      this._requestAllowed,
      this._freshRecoveryAllowed,
      this._localCleanup)
      : _revision = _vault.revision;

  static Future<AccountErasureAdapter> open({
    required ErasureReceiptVault vault,
    required ApiTransport transport,
    required ErasureFreshProvider provider,
    required bool Function() isOnline,
    required Listenable connectivity,
    required bool requestAllowed,
    bool freshRecoveryAllowed = false,
    ErasureLocalCleanup? localCleanup,
  }) async {
    final adapter = AccountErasureAdapter._(
        vault,
        transport,
        provider,
        isOnline,
        connectivity,
        requestAllowed,
        freshRecoveryAllowed,
        localCleanup);
    await adapter._restore();
    adapter.requireCurrent();
    vault.addListener(adapter._vaultChanged);
    connectivity.addListener(adapter._connectionChanged);
    return adapter;
  }

  final ErasureReceiptVault _vault;
  final ApiTransport _transport;
  final ErasureFreshProvider _provider;
  final bool Function() _isOnline;
  final Listenable _connectivity;
  final bool _requestAllowed;
  final bool _freshRecoveryAllowed;
  final ErasureLocalCleanup? _localCleanup;
  int _revision;
  bool _active = true;
  bool _busy = false;
  bool _requesting = false;
  bool _unknown = false;
  String? _job;
  final _completed = <ErasureReceiptAction>{};

  @override
  Listenable get changes => this;
  @override
  bool get online => _isOnline();
  @override
  int get generation => _active ? 0 : 1;
  @override
  bool get canRequest =>
      _active && _requestAllowed && !_unknown && _job == null;
  @override
  bool get outcomeUnknown => _unknown;
  @override
  bool get canRecoverWithProof =>
      _active && _freshRecoveryAllowed && _job == null;
  @override
  String? get jobId => _active ? _job : null;

  @override
  void requireCurrent() {
    if (!_active) throw const ErasureReceiptUnavailable();
    _vault.requireCurrent(_revision);
  }

  void _vaultChanged() {
    // Only this request's successful save is allowed to advance the revision.
    // The low-level request client still rejects invalidation/replacement races.
    if (!_active) return;
    if (_requesting) {
      try {
        _vault.requireCurrent();
        return;
      } on Object {
        // Invalidation is an owner transition even during our own save.
      }
    }
    _active = false;
    _job = null;
    notifyListeners();
  }

  void _connectionChanged() => notifyListeners();

  Future<void> _restore() async {
    requireCurrent();
    final receipt = await _vault.read();
    requireCurrent();
    final requested = await _vault.requestWasSubmitted();
    requireCurrent();
    // Recovery proves access to an old receipt, not the prior mutation outcome.
    // Retain this across disposal/process recreation, without locking normal
    // successfully acknowledged requests into read-only mode.
    var uncertain = requested && (receipt == null || receipt.recoveredByProof);
    if (receipt != null) {
      for (final action in ErasureReceiptAction.values) {
        final submitted = await _vault.actionWasSubmitted(receipt.id, action);
        requireCurrent();
        uncertain = uncertain || (submitted && !_completed.contains(action));
      }
    }
    _job = receipt?.id;
    _unknown = _unknown || uncertain;
  }

  Future<T> _run<T>(Future<T> Function() operation) async {
    requireCurrent();
    if (!online) throw const OfflineReadOnlyException();
    if (_busy) throw const ErasureReceiptUnavailable();
    _busy = true;
    try {
      final result = await operation();
      requireCurrent();
      if (!online) throw const OfflineReadOnlyException();
      return result;
    } finally {
      _busy = false;
    }
  }

  @override
  Future<Map<String, dynamic>?> readStatus() => _run(() async {
        if (_job == null) return null;
        final client = await ErasureReceiptStatusClient.open(_vault, _transport,
            isOnline: () => _active && online, connectivity: _connectivity);
        requireCurrent();
        return client.read();
      });

  @override
  Future<void> request({required bool confirmed}) => _run(() async {
        if (!confirmed || !canRequest) throw const ErasureReceiptUnavailable();
        _requesting = true;
        try {
          await ErasureFreshRequestClient(_vault, _transport,
                  isOnline: () => _active && online)
              .request(provider: _provider, confirmed: true);
          _vault.requireCurrent(_revision + 1);
          _revision++;
          await _restore();
        } on ErasureActionFailure catch (error) {
          _unknown = _unknown ||
              error.stage == ErasureActionFailureStage.outcomeUnknown;
          rethrow;
        } on Object {
          _unknown = true;
          rethrow;
        } finally {
          _requesting = false;
          // If save failed or an external owner change raced, fail closed.
          try {
            requireCurrent();
          } on Object {
            _vaultChanged();
          }
        }
      });

  Future<void> _action(ErasureReceiptAction action, bool confirmed) =>
      _run(() async {
        if (!confirmed ||
            _unknown ||
            _job == null ||
            _completed.contains(action)) {
          throw const ErasureReceiptUnavailable();
        }
        try {
          final client = await ErasureReceiptActionClient.open(
              _vault, _transport,
              isOnline: () => _active && online,
              connectivity: _connectivity,
              localCleanup: _localCleanup);
          requireCurrent();
          await client.execute(action, provider: _provider, confirmed: true);
          _completed.add(action);
        } on ErasureActionFailure catch (error) {
          _unknown = _unknown ||
              error.stage == ErasureActionFailureStage.outcomeUnknown;
          rethrow;
        }
      });

  @override
  Future<void> verify({required bool confirmed}) =>
      _action(ErasureReceiptAction.verify, confirmed);
  @override
  Future<void> cancel({required bool confirmed}) =>
      _action(ErasureReceiptAction.cancel, confirmed);

  @override
  Future<void> recoverReceipt({required bool confirmed}) => _run(() async {
        if (!confirmed) throw const ErasureReceiptUnavailable();
        await _restore();
      });

  @override
  Future<void> recoverWithProof({required bool confirmed}) => _run(() async {
        if (!confirmed || !canRecoverWithProof) {
          throw const ErasureReceiptUnavailable();
        }
        _requesting =
            true; // Permit only this operation's own receipt revision.
        try {
          await ErasureFreshRecoveryClient(_vault, _transport,
                  isOnline: () => _active && online)
              .recover(provider: _provider, confirmed: true);
          _vault.requireCurrent(_revision + 1);
          _revision++;
          await _restore(); // Unknown mutation markers deliberately remain latched.
        } finally {
          _requesting = false;
          try {
            requireCurrent();
          } on Object {
            _vaultChanged();
          }
        }
      });

  @override
  void dispose() {
    _vault.removeListener(_vaultChanged);
    _connectivity.removeListener(_connectionChanged);
    _active = false;
    _job = null;
    // Invalidate clients already awaiting transport/provider responses.
    _vault.invalidate();
    // Existing routes may outlive their owner context. Clear their projection
    // synchronously before ChangeNotifier disposes its listeners.
    notifyListeners();
    super.dispose();
  }
}
