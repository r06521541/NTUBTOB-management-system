import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/identity_link.dart';
import 'package:ntubtob_portal/integration.dart';

class FakeTransport implements ApiTransport {
  final calls = <String>[];
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    calls.add(path);
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
    return const ApiResponse(200, {
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
        ids: FixedIds());
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
    await controller.begin(LoginProvider.google);
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
    await controller.begin(LoginProvider.google);
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
        ids: FixedIds());
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
}
