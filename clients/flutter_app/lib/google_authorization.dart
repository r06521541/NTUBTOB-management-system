import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:google_sign_in/google_sign_in.dart';

import 'integration.dart';

/// Fixed boundary error: no native message, profile or assertion is retained.
class GoogleAuthorizationUnavailable implements Exception {
  const GoogleAuthorizationUnavailable();
}

/// Explicit proof-only bridge. Construction does not initialize or authorize.
/// Configuration is the ordinary process-wide configuration, WITHOUT a nonce.
/// Every authorization instead passes its fresh nonce to the native request API.
/// No plugin-private transport, silent restore, cached token or login fallback.
/// The surrounding fresh provider owns currentness/online checks; the backend
/// still verifies the signed nonce, audience, subject and freshness.
class NativeGoogleAuthorization implements GoogleFreshAuthorizationPort {
  NativeGoogleAuthorization(this.platform, this.clientId, this.serverClientId)
      : _channel =
            const MethodChannel('tw.org.ntubtob.portal/google_authorization'),
        _initialize = _initializeSdk;

  @visibleForTesting
  NativeGoogleAuthorization.forTesting(
    this.platform,
    this.clientId,
    this.serverClientId, {
    required MethodChannel channel,
    required GoogleSdkInitialize initialize,
  })  : _channel = channel,
        _initialize = initialize;

  final String platform;
  final String clientId;
  final String serverClientId;
  final MethodChannel _channel;
  final GoogleSdkInitialize _initialize;
  static bool _busy = false;

  static Future<void> _initializeSdk(
          {String? clientId, required String serverClientId}) =>
      GoogleSignIn.instance
          .initialize(clientId: clientId, serverClientId: serverClientId);

  @override
  Future<String> authorize(String nonce,
      {required void Function() beforePrompt}) async {
    if (_busy) throw const GoogleAuthorizationUnavailable();
    _busy = true;
    try {
      if (nonce.length != 43 ||
          !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(nonce)) {
        throw const GoogleAuthorizationUnavailable();
      }
      beforePrompt();
      await GoogleSignInProcessInitializer.ensure(
        platform: platform,
        clientId: clientId,
        serverClientId: serverClientId,
        initialize: _initialize,
      );
      beforePrompt();
      final raw = await _channel.invokeMethod<Object>('authorize', {
        'raw_nonce': nonce,
        // Android's existing initializer deliberately ignores this value.
        'client_id': platform == 'android' ? '' : clientId,
        'server_client_id': serverClientId,
      });
      if (raw is! Map || raw.length != 1 || raw['identity_token'] is! String) {
        throw const GoogleAuthorizationUnavailable();
      }
      final token = raw['identity_token'] as String;
      if (token.isEmpty || token.length > 16384) {
        throw const GoogleAuthorizationUnavailable();
      }
      final match = RegExp(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$')
          .firstMatch(token);
      if (match == null || match.end != token.length) {
        throw const GoogleAuthorizationUnavailable();
      }
      return token;
    } on Object {
      throw const GoogleAuthorizationUnavailable();
    } finally {
      _busy = false;
    }
  }
}
