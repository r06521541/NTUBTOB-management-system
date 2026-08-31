import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/identity_link.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/main.dart' as entrypoint;
import 'package:ntubtob_portal/production_demo.dart';

class AppleTransport implements ApiTransport {
  final responses = <Object>[];
  final calls =
      <(String, String, Map<String, String>, Map<String, dynamic>?)>[];

  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    calls.add((method, path, headers, body));
    final response = responses.removeAt(0);
    if (response is ApiResponse) return response;
    throw response;
  }
}

class FakeApple implements AppleLoginPort {
  FakeApple({
    this.token = 'header.payload.signature',
    this.code = 'fictional-single-use-authorization-code',
    this.error,
    this.pending,
  });

  final String token;
  final String code;
  final Object? error;
  final Completer<AppleAuthorizationEnvelope>? pending;
  final nonces = <String>[];

  @override
  Future<String> login(String nonce) async =>
      (await authorize(nonce)).identityToken;

  @override
  Future<AppleAuthorizationEnvelope> authorize(String nonce) async {
    nonces.add(nonce);
    if (error != null) throw error!;
    if (pending != null) return pending!.future;
    return AppleAuthorizationEnvelope(token, code);
  }
}

class AppleIds extends SecureIds {
  var index = 0;

  @override
  String next() => [
        'apple-attempt-1234567890',
        'apple-raw-nonce-1234567890',
        'apple-link-nonce-1234567890',
        'apple-link-attempt-1234567890',
      ][index++];
}

class AppleIdentityCredentials implements IdentityCredentialPort {
  final calls = <(LoginProvider, String?)>[];

  @override
  Future<String?> authenticate(LoginProvider provider, {String? nonce}) async {
    calls.add((provider, nonce));
    return 'header.payload.signature';
  }

  @override
  Future<void> clearPresentationState() async {}
}

class AppleIdentityTransport implements ApiTransport {
  final calls = <(String, Map<String, dynamic>?)>[];

  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    calls.add((path, body));
    if (path == '/auth/identities') {
      return const ApiResponse(200, {'items': []});
    }
    if (path == '/auth/identity-link/candidates/apple') {
      return const ApiResponse(
        201,
        {'candidate_credential': 'candidate', 'expires_in': 300},
      );
    }
    throw StateError('unexpected path');
  }
}

SessionEnvelope appleSession() => const SessionEnvelope(
      accessToken: 'access-token',
      refreshToken: 'refresh-token-with-at-least-32-characters',
      sessionId: 'session-id',
      expiresIn: 900,
    );

Map<String, dynamic> sessionJson() => {
      'access_token': appleSession().accessToken,
      'refresh_token': appleSession().refreshToken,
      'session_id': appleSession().sessionId,
      'expires_in': appleSession().expiresIn,
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
      'native channel accepts exact credential envelope and sends only raw nonce',
      () async {
    const channel = MethodChannel('test/apple-authorization');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    MethodCall? observed;
    messenger.setMockMethodCallHandler(channel, (call) async {
      observed = call;
      return {
        'identity_token': 'header.payload.signature',
        'authorization_code': 'fictional-single-use-code',
      };
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

    const login = NativeAppleLogin(channel: channel);
    final envelope = await login.authorize('obvious-fictional-raw-nonce');
    expect(envelope.identityToken, 'header.payload.signature');
    expect(envelope.authorizationCode, 'fictional-single-use-code');
    expect(observed?.method, 'authorize');
    expect(observed?.arguments, {'raw_nonce': 'obvious-fictional-raw-nonce'});

    messenger.setMockMethodCallHandler(
        channel,
        (_) async => {
              'identity_token': 'header.payload.signature',
              'authorization_code': 'fictional-single-use-code',
              'email': 'must-not-cross-bridge@example.invalid',
            });
    await expectLater(
      login.authorize('another-fictional-raw-nonce'),
      throwsA(isA<ContractException>()),
    );

    final oversizedToken =
        '${List.filled(8192, 'a').join()}.${List.filled(8192, 'b').join()}.c';
    messenger.setMockMethodCallHandler(
      channel,
      (_) async => {
        'identity_token': oversizedToken,
        'authorization_code': 'fictional-single-use-code',
      },
    );
    await expectLater(
      login.authorize('oversized-fictional-raw-nonce'),
      throwsA(isA<ContractException>()),
    );
  });

  test('Apple success exchanges nonce-bound token and stores session',
      () async {
    final api = AppleTransport()
      ..responses.add(ApiResponse(201, sessionJson()));
    final store = MemoryStore();
    final ids = AppleIds();
    final apple = FakeApple();
    final login = AppleLoginCoordinator(
      apple,
      api,
      SessionController(api, store, 'installation-1234', ids),
      ids,
      'installation-1234',
    );

    await login.login('ios', online: true);

    expect(login.state, LoginState.authenticated);
    expect(apple.nonces, ['apple-raw-nonce-1234567890']);
    expect(api.calls.single.$2, '/auth/apple/exchange');
    expect(api.calls.single.$4, {
      'id_token': 'header.payload.signature',
      'authorization_code': 'fictional-single-use-authorization-code',
      'nonce': 'apple-raw-nonce-1234567890',
      'login_attempt_id': 'apple-attempt-1234567890',
      'installation_id': 'installation-1234',
      'platform': 'ios',
    });
    expect(api.calls.single.$4!.keys, isNot(contains('email')));
    expect(api.calls.single.$4!.keys, isNot(contains('name')));
    expect(api.calls.single.$4!.keys, isNot(contains('user')));
    expect(await store.read('refresh:installation-1234'),
        appleSession().refreshToken);
  });

  test('Apple pending response stays review-only and stores no session',
      () async {
    final api = AppleTransport()
      ..responses.add(const ApiResponse(202, {
        'review_credential': 'apple-review-only',
        'expires_in': 600,
        'status': 'pending',
      }));
    final store = MemoryStore();
    final ids = AppleIds();
    final login = AppleLoginCoordinator(
      FakeApple(),
      api,
      SessionController(api, store, 'installation-1234', ids),
      ids,
      'installation-1234',
    );

    await login.login('ios', online: true);

    expect(login.state, LoginState.identityPending);
    expect(login.pendingReview?.credential, 'apple-review-only');
    expect(await store.read('refresh:installation-1234'), isNull);
  });

  test('Apple cancellation unavailable and network failures are classified',
      () async {
    for (final (error, expected) in <(Object, LoginState)>[
      (
        PlatformException(code: 'apple_authorization_cancelled'),
        LoginState.cancelled,
      ),
      (MissingPluginException('unavailable'), LoginState.unavailable),
    ]) {
      final api = AppleTransport();
      final ids = AppleIds();
      final login = AppleLoginCoordinator(
        FakeApple(error: error),
        api,
        SessionController(api, MemoryStore(), 'installation-1234', ids),
        ids,
        'installation-1234',
      );
      await login.login('ios', online: true);
      expect(login.state, expected);
      expect(api.calls, isEmpty);
    }

    final api = AppleTransport()..responses.add(const NetworkException());
    final ids = AppleIds();
    final login = AppleLoginCoordinator(
      FakeApple(),
      api,
      SessionController(api, MemoryStore(), 'installation-1234', ids),
      ids,
      'installation-1234',
    );
    await login.login('ios', online: true);
    expect(login.state, LoginState.recoverableError);
  });

  test('Apple offline and unsupported platforms make zero native or API calls',
      () async {
    for (final (platform, online, expected) in <(String, bool, LoginState)>[
      ('ios', false, LoginState.offline),
      ('android', true, LoginState.unavailable),
      ('windows', true, LoginState.unavailable),
    ]) {
      final api = AppleTransport();
      final ids = AppleIds();
      final apple = FakeApple();
      final login = AppleLoginCoordinator(
        apple,
        api,
        SessionController(api, MemoryStore(), 'installation-1234', ids),
        ids,
        'installation-1234',
      );
      await login.login(platform, online: online);
      expect(login.state, expected);
      expect(apple.nonces, isEmpty);
      expect(api.calls, isEmpty);
    }
  });

  test('Apple timeout remains locked and late completion never exchanges',
      () async {
    final native = Completer<AppleAuthorizationEnvelope>();
    final api = AppleTransport();
    final ids = AppleIds();
    final login = AppleLoginCoordinator(
      FakeApple(pending: native),
      api,
      SessionController(api, MemoryStore(), 'installation-1234', ids),
      ids,
      'installation-1234',
      loginTimeout: const Duration(milliseconds: 1),
    );

    await login.login('ios', online: true);
    expect(login.state, LoginState.timeoutUnresolved);
    expect(login.nativeFlowUnresolved, isTrue);
    native.complete(const AppleAuthorizationEnvelope(
      'header.payload.signature',
      'fictional-single-use-authorization-code',
    ));
    await pumpEventQueue();
    expect(login.state, LoginState.timeoutResolved);
    expect(login.nativeFlowUnresolved, isFalse);
    expect(api.calls, isEmpty);
  });

  testWidgets('Apple identity link is iOS-only and sends no profile hints',
      (tester) async {
    final api = AppleIdentityTransport();
    final credentials = AppleIdentityCredentials();
    final controller = IdentityLinkController(
      transport: api,
      credentials: credentials,
      installationId: 'installation-1234',
      ids: AppleIds(),
      authorizedSend: (method, path, {body}) =>
          api.send(method, path, body: body),
    );
    await controller.loadLinkedMethods();

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: IdentityLinkPanel(controller: controller, platform: 'android'),
      ),
    ));
    expect(
        find.byKey(const ValueKey('identity-link-begin-apple')), findsNothing);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: IdentityLinkPanel(controller: controller, platform: 'ios'),
      ),
    ));
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-apple')));
    await tester.pump();

    expect(credentials.calls.single.$1, LoginProvider.apple);
    expect(credentials.calls.single.$2, 'apple-attempt-1234567890');
    final candidate = api.calls.last;
    expect(candidate.$1, '/auth/identity-link/candidates/apple');
    expect(candidate.$2, {
      'id_token': 'header.payload.signature',
      'nonce': 'apple-attempt-1234567890',
      'login_attempt_id': 'apple-raw-nonce-1234567890',
      'installation_id': 'installation-1234',
    });
    expect(candidate.$2!.keys, isNot(contains('email')));
    expect(candidate.$2!.keys, isNot(contains('name')));
    expect(candidate.$2!.keys, isNot(contains('user')));
  });

  testWidgets(
      'Apple login action appears only when iOS composition supplies it',
      (tester) async {
    var calls = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        floatingActionButton: LoginActionButton(
          state: AuthViewState.loggedOut,
          onLogin: () {},
          onAppleLogin: () => calls++,
        ),
      ),
    ));
    expect(find.text('使用 Apple 登入'), findsOneWidget);
    await tester.tap(find.text('使用 Apple 登入'));
    expect(calls, 1);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        floatingActionButton: LoginActionButton(
          state: AuthViewState.loggedOut,
          onLogin: () {},
        ),
      ),
    ));
    expect(find.text('使用 Apple 登入'), findsNothing);
  });

  test('development fake composition has no real Apple auth root', () {
    final root = entrypoint.composeRoot(
      AppConfig.parse(flavor: 'development', mode: 'fake'),
    );
    expect(root, isA<ProductionDemoApp>());
    expect(root, isNot(isA<BasicBootstrapApp>()));
  });

  test('iOS source hashes nonce and returns no Apple profile fields', () {
    final root = Directory.current.path.endsWith('flutter_app')
        ? Directory.current
        : Directory('clients/flutter_app');
    final bridge =
        File('${root.path}/ios/Runner/AppleAuthorizationBridge.swift')
            .readAsStringSync();
    final appDelegate =
        File('${root.path}/ios/Runner/AppDelegate.swift').readAsStringSync();
    final project = File('${root.path}/ios/Runner.xcodeproj/project.pbxproj')
        .readAsStringSync();
    final marker = File(
      '${root.path}/ios/Flutter/StoreReleaseContract.xcconfig',
    ).readAsStringSync();

    expect(bridge, contains('import AuthenticationServices'));
    expect(bridge, contains('SHA256.hash(data: Data(value.utf8))'));
    expect(bridge, contains('request.nonce = Self.sha256Hex(rawNonce)'));
    expect(bridge, contains('request.requestedScopes = []'));
    expect(bridge, contains('tokenData.count <= 16_384'));
    expect(bridge, isNot(contains('tokenData.count <= 32_768')));
    expect(
      bridge,
      contains(
        'complete(["identity_token": token, "authorization_code": code])',
      ),
    );
    expect(bridge, isNot(contains('credential.email')));
    expect(bridge, isNot(contains('credential.fullName')));
    expect(bridge, isNot(contains('credential.user')));
    expect(appDelegate, contains('AppleAuthorizationBridge.register'));
    expect(project, contains('AppleAuthorizationBridge.swift in Sources'));
    expect(marker, contains('APPLE_SIGN_IN_REPOSITORY_STATUS=not_implemented'));
  });
}
