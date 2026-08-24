import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/identity_link.dart';
import 'package:ntubtob_portal/integration.dart';

class FakeTransport implements ApiTransport {
  FakeTransport({this.confirmResponse, this.throwCancel = false});
  final ApiResponse? confirmResponse;
  final bool throwCancel;
  final calls = <String>[];
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    calls.add(path);
    if (throwCancel && path.endsWith('/cancel')) {
      throw const NetworkException();
    }
    if (path == '/auth/identities') {
      return const ApiResponse(200, {
        'items': [
          {
            'provider': 'line',
            'label': 'LINE',
            'linked_at': '2026-08-24T00:00:00Z'
          }
        ]
      });
    }
    if (path.contains('/candidates/')) {
      return const ApiResponse(201, {'candidate_credential': 'candidate'});
    }
    if (path.contains('/proofs/')) {
      return const ApiResponse(201, {
        'proof_credential': 'proof',
        'person': {'display_name': '安全帳戶'}
      });
    }
    return confirmResponse ??
        const ApiResponse(200, {
          'status': 'linked',
          'session': {
            'access_token': 'access-token',
            'refresh_token': 'refresh-token',
            'session_id': 'session-id',
            'expires_in': 900
          }
        });
  }
}

class FakeCredentials implements IdentityCredentialPort {
  FakeCredentials({this.throwOnClear = false});
  final bool throwOnClear;
  int calls = 0, clears = 0;
  String? token = 'id-token';
  @override
  Future<String?> authenticate(LoginProvider provider, {String? nonce}) async {
    calls++;
    return token;
  }

  @override
  Future<void> clearPresentationState() async {
    clears++;
    if (throwOnClear) throw StateError('provider clear failed');
  }
}

class DelayedIdentityListTransport extends FakeTransport {
  final response = Completer<ApiResponse>();
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {}, Map<String, dynamic>? body}) {
    if (path == '/auth/identities') return response.future;
    return super.send(method, path, headers: headers, body: body);
  }
}

class AuthFlowTransport implements ApiTransport {
  AuthFlowTransport({this.terminal = false});
  final bool terminal;
  final calls = <(String, String, Map<String, String>)>[];
  int protectedCalls = 0;
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    calls.add((method, path, headers));
    if (path == '/auth/refresh') {
      return const ApiResponse(200, {
        'access_token': 'new-access',
        'refresh_token': 'new-refresh-token',
        'session_id': 'session-id',
        'expires_in': 900,
      });
    }
    if (path == '/auth/identities' || path.endsWith('/confirm')) {
      protectedCalls++;
      if (protectedCalls == 1 || terminal) return const ApiResponse(401, null);
      if (path == '/auth/identities') {
        return const ApiResponse(200, {'items': []});
      }
      return const ApiResponse(200, {'status': 'linked', 'session': null});
    }
    if (path.contains('/candidates/')) {
      return const ApiResponse(201, {'candidate_credential': 'candidate'});
    }
    if (path.contains('/proofs/')) {
      return const ApiResponse(201, {
        'proof_credential': 'proof',
        'person': {'display_name': 'Safe'}
      });
    }
    throw StateError('unexpected path $path');
  }
}

class FixedIds extends SecureIds {
  @override
  String next() => 'attempt-1234567890';
}

void main() {
  testWidgets('provider UI is explicit tap only and cancel retires memory',
      (tester) async {
    final api = FakeTransport(), credentials = FakeCredentials();
    final controller = IdentityLinkController(
        transport: api,
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds(),
        authorizedSend: (method, path, {body}) =>
            api.send(method, path, body: body));
    await controller.loadLinkedMethods();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: IdentityLinkPanel(
                controller: controller, platform: 'android'))));
    expect(credentials.calls, 0);
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    expect(credentials.calls, 1);
    expect(controller.candidateCredential, 'candidate');
    await tester.tap(find.byKey(const ValueKey('identity-link-cancel')));
    await tester.pump();
    expect(controller.candidateCredential, isNull);
    expect(credentials.clears, 1);
  });
  testWidgets('offline never calls provider or backend', (tester) async {
    final api = FakeTransport(), credentials = FakeCredentials();
    final controller = IdentityLinkController(
        transport: api,
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds(),
        online: false);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: IdentityLinkPanel(
                controller: controller, platform: 'android'))));
    expect(find.byKey(const ValueKey('identity-link-offline')), findsOneWidget);
    expect(credentials.calls, 0);
    expect(api.calls, isEmpty);
  });
  test('terminal clears credentials and provider presentation state', () async {
    final credentials = FakeCredentials();
    final controller = IdentityLinkController(
        transport: FakeTransport(),
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds());
    await controller.begin(LoginProvider.google, recovery: true);
    await controller.terminal();
    expect(controller.candidateCredential, isNull);
    expect(credentials.clears, 1);
  });

  test('person switch retires all in-memory proof and provider state',
      () async {
    final credentials = FakeCredentials();
    final controller = IdentityLinkController(
        transport: FakeTransport(),
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds());
    await controller.begin(LoginProvider.google, recovery: true);
    await controller.prove(LoginProvider.line);
    await controller.personSwitch();
    expect(controller.stage, IdentityLinkStage.idle);
    expect(controller.candidateCredential, isNull);
    expect(controller.proofCredential, isNull);
    expect(credentials.clears, 1);
  });

  testWidgets('account list is redacted and hides already linked provider',
      (tester) async {
    final controller = IdentityLinkController(
        transport: FakeTransport(),
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds(),
        authorizedSend: (method, path, {body}) =>
            FakeTransport().send(method, path, body: body));
    await controller.loadLinkedMethods();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: IdentityLinkPanel(
                controller: controller, platform: 'android'))));
    expect(find.byKey(const ValueKey('linked-provider-line')), findsOneWidget);
    expect(
        find.byKey(const ValueKey('identity-link-begin-line')), findsNothing);
    expect(find.byKey(const ValueKey('identity-link-begin-google')),
        findsOneWidget);
  });

  testWidgets('self-link stays disabled until identity list succeeds',
      (tester) async {
    final controller = IdentityLinkController(
        transport: FakeTransport(),
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds());
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: IdentityLinkPanel(
                controller: controller, platform: 'android'))));
    expect(
        find.byKey(const ValueKey('identity-link-begin-google')), findsNothing);
    expect(
        find.byKey(const ValueKey('identity-link-begin-line')), findsNothing);
  });

  test('self identity list uses bearer refresh and one authorized retry',
      () async {
    final api = AuthFlowTransport();
    final store = MemoryStore();
    final sessions =
        SessionController(api, store, 'installation-1234', FixedIds());
    await sessions.accept(const SessionEnvelope(
        accessToken: 'old-access',
        refreshToken: 'old-refresh-token',
        sessionId: 'session-id',
        expiresIn: 900));
    final controller = IdentityLinkController(
        transport: api,
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds(),
        session: sessions);
    await controller.loadLinkedMethods();
    expect(controller.linkedMethodsLoaded, isTrue);
    expect(api.calls.first.$3['Authorization'], 'Bearer old-access');
    expect(api.calls.last.$3['Authorization'], 'Bearer new-access');
    expect(api.calls.where((call) => call.$2 == '/auth/refresh'), hasLength(1));
  });

  test('terminal authorized failure propagates purge after local retirement',
      () async {
    final api = AuthFlowTransport(terminal: true);
    final store = MemoryStore();
    final sessions =
        SessionController(api, store, 'installation-1234', FixedIds());
    await sessions.accept(const SessionEnvelope(
        accessToken: 'old-access',
        refreshToken: 'old-refresh-token',
        sessionId: 'session-id',
        expiresIn: 900));
    var terminalCalls = 0;
    final controller = IdentityLinkController(
        transport: api,
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds(),
        session: sessions,
        onTerminalSession: () async => terminalCalls++);
    await controller.loadLinkedMethods();
    expect(terminalCalls, 1);
    expect(controller.stage, IdentityLinkStage.idle);
    expect(controller.linkedMethodsLoaded, isFalse);
    expect(await store.read('refresh:installation-1234'), isNull);
  });

  test('self confirm is authorized while recovery transport has no bearer',
      () async {
    final api = AuthFlowTransport();
    final store = MemoryStore();
    final sessions =
        SessionController(api, store, 'installation-1234', FixedIds());
    await sessions.accept(const SessionEnvelope(
        accessToken: 'old-access',
        refreshToken: 'old-refresh-token',
        sessionId: 'session-id',
        expiresIn: 900));
    final controller = IdentityLinkController(
        transport: api,
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds(),
        session: sessions);
    await controller.loadLinkedMethods();
    await controller.begin(LoginProvider.google);
    await controller.prove(LoginProvider.line);
    await controller.confirm(recovery: false, platform: 'android');
    final confirm = api.calls.lastWhere((call) => call.$2.endsWith('/confirm'));
    expect(confirm.$3['Authorization'], 'Bearer new-access');

    final raw = FakeTransport();
    final recoveryStore = MemoryStore();
    final recovery = IdentityLinkController(
        transport: raw,
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds(),
        session: SessionController(
            raw, recoveryStore, 'installation-1234', FixedIds()));
    await recovery.begin(LoginProvider.google, recovery: true);
    await recovery.prove(LoginProvider.line);
    await recovery.confirm(recovery: true, platform: 'android');
    expect(raw.calls.where((path) => path == '/auth/refresh'), isEmpty);
  });

  test('stale identity list cannot cross terminal principal boundary',
      () async {
    final api = DelayedIdentityListTransport();
    final controller = IdentityLinkController(
        transport: api,
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds(),
        authorizedSend: (method, path, {body}) =>
            api.send(method, path, body: body));
    final pending = controller.loadLinkedMethods();
    await controller.personSwitch();
    api.response.complete(const ApiResponse(200, {
      'items': [
        {
          'provider': 'line',
          'label': 'LINE A',
          'linked_at': '2026-08-24T00:00:00Z'
        }
      ]
    }));
    await pending;
    expect(controller.linkedMethods, isEmpty);
    expect(controller.linkedMethodsLoaded, isFalse);
  });

  test('cancel retires synchronously despite backend and provider failures',
      () async {
    final credentials = FakeCredentials(throwOnClear: true);
    final controller = IdentityLinkController(
        transport: FakeTransport(throwCancel: true),
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds());
    await controller.begin(LoginProvider.google, recovery: true);
    await controller.cancel();
    expect(controller.stage, IdentityLinkStage.cancelled);
    expect(controller.candidateCredential, isNull);
    expect(controller.linkedMethodsLoaded, isFalse);
    expect(credentials.clears, 1);
    await controller.cancel();
    expect(credentials.clears, 1);
  });

  test('expired recovery proof retires credentials before showing error',
      () async {
    final credentials = FakeCredentials();
    final controller = IdentityLinkController(
        transport: FakeTransport(
            confirmResponse: const ApiResponse(401, {
          'error': {'code': 'identity_link_proof_expired'}
        })),
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds());
    await controller.begin(LoginProvider.google, recovery: true);
    await controller.prove(LoginProvider.line);
    await controller.confirm(recovery: true, platform: 'android');
    expect(controller.stage, IdentityLinkStage.error);
    expect(controller.candidateCredential, isNull);
    expect(controller.proofCredential, isNull);
    expect(credentials.clears, 1);
  });

  test('lost response replay never mutates session or claims authenticated',
      () async {
    final api = FakeTransport(
        confirmResponse: const ApiResponse(
            200, {'status': 'already_linked', 'session': null}));
    final store = MemoryStore();
    final controller = IdentityLinkController(
        transport: api,
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds(),
        session:
            SessionController(api, store, 'installation-1234', FixedIds()));
    await controller.begin(LoginProvider.google, recovery: true);
    await controller.prove(LoginProvider.line);
    await controller.confirm(recovery: true, platform: 'android');
    expect(controller.stage, IdentityLinkStage.reauthenticationRequired);
    expect(await store.read('refresh:installation-1234'), isNull);
  });

  test('recovery rejects missing session and wrong status', () async {
    for (final response in const [
      ApiResponse(200, {'status': 'linked', 'session': null}),
      ApiResponse(200, {'status': 'pending', 'session': null}),
      ApiResponse(200, {
        'status': 'linked',
        'session': {'expires_in': 900}
      }),
    ]) {
      final api = FakeTransport(confirmResponse: response);
      final store = MemoryStore();
      final controller = IdentityLinkController(
          transport: api,
          credentials: FakeCredentials(),
          installationId: 'installation-1234',
          ids: FixedIds(),
          session:
              SessionController(api, store, 'installation-1234', FixedIds()));
      await controller.begin(LoginProvider.google, recovery: true);
      await controller.prove(LoginProvider.line);
      await controller.confirm(recovery: true, platform: 'android');
      expect(controller.stage, IdentityLinkStage.error);
      expect(await store.read('refresh:installation-1234'), isNull);
    }
  });

  testWidgets('recovery requires two explicit different-provider taps',
      (tester) async {
    final api = FakeTransport(), credentials = FakeCredentials();
    final store = MemoryStore();
    var recovered = 0;
    final controller = IdentityLinkController(
        transport: api,
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds(),
        session: SessionController(api, store, 'installation-1234', FixedIds()),
        onRecovered: () async => recovered++);
    await tester.pumpWidget(MaterialApp(
        home:
            IdentityRecoveryPage(controller: controller, platform: 'android')));
    expect(credentials.calls, 0);
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('identity-link-proof-line')));
    await tester.pump();
    expect(credentials.calls, 2);
    expect(find.text('確認追認並登入'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('identity-link-confirm')));
    await tester.pump();
    expect(api.calls.where((path) => path.endsWith('/confirm')).length, 1);
    expect(controller.stage, IdentityLinkStage.completed);
    expect(await store.read('refresh:installation-1234'), 'refresh-token');
    expect(recovered, 1);
  });

  testWidgets('recovery cancel retires route once and cannot resend cancel',
      (tester) async {
    final api = FakeTransport();
    final controller = IdentityLinkController(
        transport: api,
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds());
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => ElevatedButton(
          key: const ValueKey('open-recovery'),
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => IdentityRecoveryPage(
                controller: controller, platform: 'android'),
          )),
          child: const Text('open'),
        ),
      ),
    ));
    await tester.tap(find.byKey(const ValueKey('open-recovery')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('identity-link-cancel')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('open-recovery')), findsOneWidget);
    expect(api.calls.where((path) => path.endsWith('/cancel')), hasLength(1));
    await controller.cancel();
    expect(api.calls.where((path) => path.endsWith('/cancel')), hasLength(1));
  });

  testWidgets('recovery success and terminal state both retire the route',
      (tester) async {
    final api = FakeTransport();
    final controller = IdentityLinkController(
        transport: api,
        credentials: FakeCredentials(),
        installationId: 'installation-1234',
        ids: FixedIds(),
        session: SessionController(
            api, MemoryStore(), 'installation-1234', FixedIds()));
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => ElevatedButton(
          key: const ValueKey('open-recovery'),
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => IdentityRecoveryPage(
                controller: controller, platform: 'android'),
          )),
          child: const Text('open'),
        ),
      ),
    ));

    await tester.tap(find.byKey(const ValueKey('open-recovery')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('identity-link-proof-line')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('identity-link-confirm')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('open-recovery')), findsOneWidget);

    await controller.terminal();
    await tester.tap(find.byKey(const ValueKey('open-recovery')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    await controller.terminal();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('open-recovery')), findsOneWidget);
  });

  testWidgets(
      'recovery error retires route and a new flow requires two fresh taps',
      (tester) async {
    final api = FakeTransport(
        confirmResponse: const ApiResponse(401, {
      'error': {'code': 'identity_link_proof_expired'}
    }));
    final credentials = FakeCredentials();
    final controller = IdentityLinkController(
        transport: api,
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds());
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => ElevatedButton(
          key: const ValueKey('open-recovery'),
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => IdentityRecoveryPage(
                controller: controller, platform: 'android'),
          )),
          child: const Text('open'),
        ),
      ),
    ));

    await tester.tap(find.byKey(const ValueKey('open-recovery')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('identity-link-proof-line')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('identity-link-confirm')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('open-recovery')), findsOneWidget);
    expect(controller.stage, IdentityLinkStage.idle);
    expect(controller.candidateCredential, isNull);
    expect(controller.proofCredential, isNull);

    await tester.tap(find.byKey(const ValueKey('open-recovery')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    expect(controller.stage, IdentityLinkStage.candidateReady);
    expect(find.byKey(const ValueKey('identity-link-confirm')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('identity-link-proof-line')));
    await tester.pump();
    expect(controller.stage, IdentityLinkStage.proofReady);
    expect(credentials.calls, 4);
  });

  testWidgets('self-link error reloads methods and permits a fresh retry',
      (tester) async {
    final api = FakeTransport(
        confirmResponse: const ApiResponse(500, {
      'error': {'code': 'internal'}
    }));
    final credentials = FakeCredentials();
    final controller = IdentityLinkController(
        transport: api,
        credentials: credentials,
        installationId: 'installation-1234',
        ids: FixedIds(),
        authorizedSend: (method, path, {body}) =>
            api.send(method, path, body: body));
    await controller.loadLinkedMethods();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: IdentityLinkPanel(
                controller: controller, platform: 'android'))));
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('identity-link-proof-line')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('identity-link-confirm')));
    await tester.pump();
    expect(find.byKey(const ValueKey('identity-link-error')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('identity-link-retry')));
    await tester.pump();
    expect(controller.stage, IdentityLinkStage.idle);
    expect(controller.linkedMethodsLoaded, isTrue);
    expect(find.byKey(const ValueKey('identity-link-begin-google')),
        findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('identity-link-begin-google')));
    await tester.pump();
    expect(controller.stage, IdentityLinkStage.candidateReady);
    expect(credentials.calls, 3);
  });
}
