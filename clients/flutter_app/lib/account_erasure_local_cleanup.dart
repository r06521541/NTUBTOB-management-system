import 'dart:async';

import 'account_erasure_client.dart';
import 'integration.dart';

/// Explicit composition only: no native enablement or provider logout.
/// Capture when the original business owner authorizes the receipt flow. Never
/// recreate this helper by accepting whichever session happens to be current.
/// The receipt vault and fresh-proof owner must use their own lifetime: our one
/// intentional business generation change is not a receipt-owner transition.
class SessionBoundErasureCleanup implements ErasureLocalCleanup {
  SessionBoundErasureCleanup(this._session)
      : _originalGeneration = _session.generation {
    if (_session.terminalPurge == null) {
      throw const ErasureReceiptUnavailable();
    }
  }

  final SessionController _session;
  final int _originalGeneration;
  Future<void>? _operation;
  bool _started = false;
  bool _failed = false;

  @override
  void requireCurrent() {
    final expected = _originalGeneration + (_started ? 1 : 0);
    if (_failed || _session.generation != expected) {
      throw const ErasureReceiptUnavailable();
    }
  }

  @override
  Future<void> clearBeforeVerification() {
    requireCurrent();
    final existing = _operation;
    if (existing != null) return existing;
    final completion = Completer<void>();
    // Reserve before clear synchronously notifies business-generation observers.
    _operation = completion.future;
    _started = true;
    try {
      final clearing = _session.clear(expectedGeneration: _originalGeneration);
      unawaited(_finish(clearing, completion));
    } on Object {
      _failed = true;
      completion.completeError(const ErasureReceiptUnavailable());
    }
    return completion.future;
  }

  Future<void> _finish(
      Future<void> clearing, Completer<void> completion) async {
    try {
      await clearing;
      requireCurrent();
      completion.complete();
    } on Object {
      _failed = true;
      // SessionController retains cleanup debt and blocks credential publication.
      // Never leak a platform storage exception or treat partial cleanup as done.
      completion.completeError(const ErasureReceiptUnavailable());
    }
  }
}
