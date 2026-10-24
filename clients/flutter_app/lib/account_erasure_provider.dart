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
      required bool Function() isOnline})
      : super('apple', apple.login, requireCurrent, isOnline);
}

class LineErasureFreshProvider extends _NonceErasureProvider {
  LineErasureFreshProvider(LineLoginPort line,
      {required void Function() requireCurrent,
      required bool Function() isOnline})
      : super('line', line.login, requireCurrent, isOnline);
}

class GoogleErasureFreshProvider extends _NonceErasureProvider {
  GoogleErasureFreshProvider(GoogleFreshAuthorizationPort google,
      {required void Function() requireCurrent,
      required bool Function() isOnline})
      : super(
            'google',
            (nonce) => google.authorize(nonce, beforePrompt: () {
                  requireCurrent();
                  if (!isOnline())
                    throw const ErasureFreshProviderUnavailable();
                }),
            requireCurrent,
            isOnline);
}

abstract class _NonceErasureProvider implements ErasureFreshProvider {
  _NonceErasureProvider(
      this.provider, this._authorize, this._requireCurrent, this._isOnline);

  @override
  final String provider;
  final Future<String> Function(String) _authorize;
  final void Function() _requireCurrent;
  final bool Function() _isOnline;
  bool _busy = false;

  void _current() {
    _requireCurrent();
    if (!_isOnline()) throw const ErasureFreshProviderUnavailable();
  }

  @override
  Future<String> authenticate(String nonce) async {
    if (_busy) throw const ErasureFreshProviderUnavailable();
    _busy = true;
    try {
      _current();
      if (nonce.length != 43 ||
          !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(nonce)) {
        throw const ErasureFreshProviderUnavailable();
      }
      final assertion = await _authorize(nonce);
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
