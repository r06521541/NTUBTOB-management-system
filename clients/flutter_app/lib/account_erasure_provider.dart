import 'account_erasure_client.dart';
import 'integration.dart';

/// Fixed diagnostic: never expose native errors or assertion contents.
class ErasureFreshProviderUnavailable implements Exception {
  const ErasureFreshProviderUnavailable();
}

/// Proof-only adapters. The currentness callback must be bound to the original
/// owner generation, not a getter accepting whichever owner is now signed in.
/// Existing native ports receive the fresh server nonce on every authorization;
/// server-side verification remains mandatory. No session exchange or enrollment
/// occurs here. Google uses its separate fresh port, never ordinary login.
class AppleErasureFreshProvider extends _NonceErasureProvider {
  AppleErasureFreshProvider(AppleLoginPort apple,
      {required void Function() requireCurrent,
      required bool Function() isOnline,
      Future<void> Function()? afterAuthorization})
      : super(
            'apple', apple.login, requireCurrent, isOnline, afterAuthorization);
}

class LineErasureFreshProvider extends _NonceErasureProvider {
  LineErasureFreshProvider(LineLoginPort line,
      {required void Function() requireCurrent,
      required bool Function() isOnline,
      Future<void> Function()? afterAuthorization})
      : super('line', line.login, requireCurrent, isOnline, afterAuthorization);
}

class GoogleErasureFreshProvider extends _NonceErasureProvider {
  GoogleErasureFreshProvider(GoogleFreshAuthorizationPort google,
      {required void Function() requireCurrent,
      required bool Function() isOnline,
      Future<void> Function()? afterAuthorization})
      : super(
            'google',
            (nonce) => google.authorize(nonce, beforePrompt: () {
                  requireCurrent();
                  if (!isOnline()) {
                    throw const ErasureFreshProviderUnavailable();
                  }
                }),
            requireCurrent,
            isOnline,
            afterAuthorization);
}

abstract class _NonceErasureProvider implements ErasureFreshProvider {
  _NonceErasureProvider(this.provider, this._authorize, this._requireCurrent,
      this._isOnline, this._afterAuthorization);

  @override
  final String provider;
  final Future<String> Function(String) _authorize;
  final void Function() _requireCurrent;
  final bool Function() _isOnline;
  final Future<void> Function()? _afterAuthorization;
  bool _busy = false;

  void _current() {
    _requireCurrent();
    if (!_isOnline()) {
      throw const ErasureFreshProviderUnavailable();
    }
  }

  @override
  Future<String> authenticate(String nonce) async {
    if (_busy) {
      throw const ErasureFreshProviderUnavailable();
    }
    _busy = true;
    try {
      _current();
      if (nonce.length != 43 ||
          !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(nonce)) {
        throw const ErasureFreshProviderUnavailable();
      }
      final assertion = await _authorize(nonce);
      _requireCurrent();
      // Native authorization may suspend the App. Re-establish bounded public
      // reachability before accepting its result, never repeat authorization.
      await _afterAuthorization?.call();
      _current();
      if (assertion.isEmpty || assertion.length > 16384) {
        throw const ErasureFreshProviderUnavailable();
      }
      return assertion;
    } on Object {
      throw const ErasureFreshProviderUnavailable();
    } finally {
      _busy = false;
    }
  }
}
