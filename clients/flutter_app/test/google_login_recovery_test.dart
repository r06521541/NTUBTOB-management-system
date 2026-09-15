import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/integration.dart';

class _Google implements GoogleLoginPort {
  int calls = 0;

  @override
  Future<String> login() async {
    calls++;
    return 'obvious-fake-google-token';
  }

  @override
  Future<void> logout() async {}
}

Map<String, dynamic> _error({
  String code = 'service_unavailable',
  Object retryable = true,
}) =>
    {
      'error': {
        'code': code,
        'message': 'required database revision is unavailable',
        'request_id': 'fictional-request',
        'retryable': retryable,
        'retry_after_seconds': null,
        'field_errors': <Object>[],
      },
    };

Map<String, dynamic> _details(Map<String, dynamic> changes) {
  final envelope = _error();
  (envelope['error'] as Map<String, dynamic>).addAll(changes);
  return envelope;
}

void main() {
  for (final platform in ['ios', 'android']) {
    test('Google $platform valid retryable 503 is recoverable without retry',
        () async {
      final requests = <http.Request>[];
      final client = MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_error()), 503);
      });
      addTearDown(client.close);
      final api =
          HttpApiTransport(Uri.parse('https://example.invalid'), client);
      final store = MemoryStore();
      final google = _Google();
      final sessions =
          SessionController(api, store, 'fixture-install', SecureIds());
      final login = GoogleLoginCoordinator(
          google, api, sessions, SecureIds(), 'fixture-install');
      addTearDown(login.dispose);
      final states = <LoginState>[];
      login.addListener(() => states.add(login.state));

      await login.login(platform);

      expect(login.state, LoginState.recoverableError);
      expect(states, [
        LoginState.providerActive,
        LoginState.exchanging,
        LoginState.recoverableError
      ]);
      expect(google.calls, 1);
      expect(requests, hasLength(1));
      expect(requests.single.method, 'POST');
      expect(requests.single.url.path, '/api/v1/auth/google/exchange');
      expect(jsonDecode(requests.single.body)['platform'], platform);
      expect(login.pendingReview, isNull);
      expect(sessions.accessToken, isNull);
      expect(store.values, isEmpty);
    });
  }

  final failures = <String, (int, String, LoginState)>{
    'nonretryable 503': (
      503,
      jsonEncode(_error(retryable: false)),
      LoginState.error
    ),
    'unknown code': (
      503,
      jsonEncode(_error(code: 'future_error')),
      LoginState.error
    ),
    'provider outcome unknown': (
      503,
      jsonEncode(_error(code: 'provider_outcome_unknown')),
      LoginState.error
    ),
    'wrong retryable type': (
      503,
      jsonEncode(_error(retryable: 'true')),
      LoginState.error
    ),
    'missing fields': (
      503,
      '{"error":{"code":"service_unavailable"}}',
      LoginState.error
    ),
    'non-JSON gateway': (503, '<html>unavailable</html>', LoginState.error),
    'missing body': (503, '', LoginState.error),
    'wrong status': (500, jsonEncode(_error()), LoginState.error),
    '401 status with unavailable code': (
      401,
      jsonEncode(_error()),
      LoginState.error
    ),
    '503 with authentication code': (
      503,
      jsonEncode(_error(code: 'unauthenticated')),
      LoginState.error
    ),
    '503 with expired session code': (
      503,
      jsonEncode(_error(code: 'session_expired')),
      LoginState.error
    ),
    '503 with server error code': (
      503,
      jsonEncode(_error(code: 'server_error')),
      LoginState.error
    ),
    'extra envelope field': (
      503,
      jsonEncode({..._error(), 'extra': true}),
      LoginState.error
    ),
    'extra error field': (
      503,
      jsonEncode(_details({'extra': true})),
      LoginState.error
    ),
    'negative retry delay': (
      503,
      jsonEncode(_details({'retry_after_seconds': -1})),
      LoginState.error
    ),
    'invalid field error': (
      503,
      jsonEncode(_details({
        'field_errors': [1]
      })),
      LoginState.error
    ),
    'too many field errors': (
      503,
      jsonEncode(
          _details({'field_errors': List.filled(21, <String, dynamic>{})})),
      LoginState.error
    ),
    'long message': (
      503,
      jsonEncode(_details({'message': 'x' * 301})),
      LoginState.error
    ),
    'long request ID': (
      503,
      jsonEncode(_details({'request_id': 'x' * 101})),
      LoginState.error
    ),
    'malformed success': (201, '{"expires_in":901}', LoginState.error),
    'unauthenticated': (
      401,
      jsonEncode(_error(code: 'unauthenticated')),
      LoginState.error
    ),
    'account unavailable': (
      403,
      jsonEncode(_error(code: 'account_unavailable', retryable: false)),
      LoginState.accountUnavailable
    ),
  };
  for (final entry in failures.entries) {
    test('Google ${entry.key} does not become recoverable', () async {
      var requests = 0;
      final client = MockClient((request) async {
        requests++;
        return http.Response(entry.value.$2, entry.value.$1);
      });
      addTearDown(client.close);
      final api =
          HttpApiTransport(Uri.parse('https://example.invalid'), client);
      final store = MemoryStore();
      final google = _Google();
      final sessions =
          SessionController(api, store, 'fixture-install', SecureIds());
      final login = GoogleLoginCoordinator(
          google, api, sessions, SecureIds(), 'fixture-install');
      addTearDown(login.dispose);

      await login.login('ios');

      expect(login.state, entry.value.$3);
      expect(google.calls, 1);
      expect(requests, 1);
      expect(login.pendingReview, isNull);
      expect(sessions.accessToken, isNull);
      expect(store.values, isEmpty);
    });
  }

  test('Google recoverable 503 accepts Error schema boundary values', () async {
    final client = MockClient((_) async => http.Response(
        jsonEncode(_details({
          'message': '球' * 300,
          'request_id': 'r' * 100,
          'retry_after_seconds': 0,
          'field_errors': List.filled(20, <String, dynamic>{}),
        })),
        503,
        headers: {'content-type': 'application/json; charset=utf-8'}));
    addTearDown(client.close);
    final api = HttpApiTransport(Uri.parse('https://example.invalid'), client);
    final store = MemoryStore();
    final sessions =
        SessionController(api, store, 'fixture-install', SecureIds());
    final login = GoogleLoginCoordinator(
        _Google(), api, sessions, SecureIds(), 'fixture-install');
    addTearDown(login.dispose);
    await login.login('ios');
    expect(login.state, LoginState.recoverableError);
    expect(sessions.accessToken, isNull);
    expect(store.values, isEmpty);
  });

  test('Google 202 review then 503 retires review without creating session',
      () async {
    var calls = 0;
    final client = MockClient((_) async => ++calls == 1
        ? http.Response(
            jsonEncode({
              'review_credential': 'fictional-review',
              'expires_in': 600,
              'status': 'pending',
            }),
            202)
        : http.Response(jsonEncode(_error()), 503));
    addTearDown(client.close);
    final api = HttpApiTransport(Uri.parse('https://example.invalid'), client);
    final store = MemoryStore();
    final sessions =
        SessionController(api, store, 'fixture-install', SecureIds());
    final login = GoogleLoginCoordinator(
        _Google(), api, sessions, SecureIds(), 'fixture-install');
    addTearDown(login.dispose);
    await login.login('ios');
    expect(login.state, LoginState.identityPending);
    expect(login.pendingReview?.credential, 'fictional-review');
    await login.login('ios');
    expect(login.state, LoginState.recoverableError);
    expect(login.pendingReview, isNull);
    expect(sessions.accessToken, isNull);
    expect(store.values, isEmpty);
    expect(calls, 2);
  });

  test('Google 201 still accepts a normal session', () async {
    final client = MockClient((_) async => http.Response(
        jsonEncode({
          'access_token': 'fictional-access',
          'refresh_token': 'fictional-refresh-at-least-32-characters',
          'session_id': 'fictional-session',
          'expires_in': 900,
        }),
        201));
    addTearDown(client.close);
    final api = HttpApiTransport(Uri.parse('https://example.invalid'), client);
    final store = MemoryStore();
    final sessions =
        SessionController(api, store, 'fixture-install', SecureIds());
    final login = GoogleLoginCoordinator(
        _Google(), api, sessions, SecureIds(), 'fixture-install');
    addTearDown(login.dispose);
    await login.login('ios');
    expect(login.state, LoginState.authenticated);
    expect(sessions.accessToken, 'fictional-access');
    expect(await store.read('refresh:fixture-install'),
        'fictional-refresh-at-least-32-characters');
  });

  test('Google transport uncertainty does not become recoverable', () async {
    var calls = 0;
    final client = MockClient((_) async {
      calls++;
      throw http.ClientException('fictional transport failure');
    });
    addTearDown(client.close);
    final api = HttpApiTransport(Uri.parse('https://example.invalid'), client);
    final store = MemoryStore();
    final sessions =
        SessionController(api, store, 'fixture-install', SecureIds());
    final login = GoogleLoginCoordinator(
        _Google(), api, sessions, SecureIds(), 'fixture-install');
    addTearDown(login.dispose);
    await login.login('ios');
    expect(login.state, LoginState.error);
    expect(calls, 1);
    expect(sessions.accessToken, isNull);
    expect(store.values, isEmpty);
  });

  testWidgets(
      'Google 503 shows safe recovery and requires a fresh manual action',
      (tester) async {
    final requests = <http.Request>[];
    final client = MockClient((request) async {
      requests.add(request);
      return http.Response(jsonEncode(_error()), 503);
    });
    addTearDown(client.close);
    final api = HttpApiTransport(Uri.parse('https://example.invalid'), client);
    final store = MemoryStore();
    final google = _Google();
    final sessions =
        SessionController(api, store, 'fixture-install', SecureIds());
    final login = GoogleLoginCoordinator(
        google, api, sessions, SecureIds(), 'fixture-install');
    addTearDown(login.dispose);
    await tester.pumpWidget(MaterialApp(
        home: AnimatedBuilder(
      animation: login,
      builder: (context, child) {
        final state =
            googleLoginAuthViewState(login.state, AuthViewState.loggedOut);
        return Scaffold(
          body: AuthStatePanel(state: state),
          floatingActionButton: LoginActionButton(
            state: state,
            onLogin: null,
            onGoogleLogin: () => login.login('ios'),
          ),
        );
      },
    )));
    await tester.tap(find.text('Google 登入'));
    await tester.pumpAndSettle();
    expect(find.text('連線暫時失敗，請稍後重試'), findsOneWidget);
    expect(find.text('資料格式異常，已停止處理'), findsNothing);
    expect(
        find.text('required database revision is unavailable'), findsNothing);
    expect(find.text('fictional-request'), findsNothing);
    expect(find.text('obvious-fake-google-token'), findsNothing);
    await tester.pump(const Duration(seconds: 30));
    expect(requests, hasLength(1));
    expect(google.calls, 1);
    expect(sessions.accessToken, isNull);
    expect(store.values, isEmpty);

    await tester.tap(find.text('Google 登入'));
    await tester.pumpAndSettle();
    expect(requests, hasLength(2));
    expect(google.calls, 2);
    final firstAttempt = jsonDecode(requests.first.body)['login_attempt_id'];
    final secondAttempt = jsonDecode(requests.last.body)['login_attempt_id'];
    expect(secondAttempt, isNot(firstAttempt));
    expect(store.values, isEmpty);
  });
}
