import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ntubtob_portal/account_erasure_entry.dart';
import 'package:ntubtob_portal/account_erasure_flow.dart';
import 'package:ntubtob_portal/account_erasure_owner.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/identity_link.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/local_preferences.dart';

import 'account_erasure_action_test.dart' as fixture;
import 'account_erasure_local_cleanup_test.dart' as cleanup_fixture;
import 'account_erasure_owner_test.dart' as owner_fixture;
import 'account_erasure_provider_test.dart' as provider_fixture;

class RootHttp extends MockClient {
  RootHttp(this.handler) : super(handler);
  final Future<http.Response> Function(http.Request) handler;
  bool closed = false;
  @override
  void close() {
    closed = true;
    super.close();
  }
}

void rootTestWidgets(
    String description, Future<void> Function(WidgetTester) body) {
  testWidgets(description, (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      await body(tester);
    } finally {
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    }
  });
}

void main() {
  late MemoryStore store;
  late ValueNotifier<bool> online;
  late provider_fixture.ProofPorts ports;
  late owner_fixture.OwnerTransport erasureTransport;
  late RootHttp httpClient;
  late AccountErasureEntryOptions options;
  final contexts = <AccountErasureRootContext>[];
  final owners = <AccountErasureOwner>[];
  final requests = <http.Request>[];

  setUp(() async {
    store = MemoryStore();
    store.values['installation:v1'] = 'fixture';
    await LocalPreferences(store, 'fixture').completeOnboarding();
    online = ValueNotifier(true);
    ports = provider_fixture.ProofPorts();
    erasureTransport = owner_fixture.OwnerTransport();
    contexts.clear();
    owners.clear();
    requests.clear();
    httpClient = RootHttp((request) async {
      requests.add(request);
      final path = request.url.path.replaceFirst('/api/v1', '');
      if (path.startsWith('/account-erasure/')) {
        expect(request.headers.containsKey('authorization'), isFalse);
        final response = await erasureTransport.send(request.method, path,
            body: jsonDecode(request.body) as Map<String, dynamic>);
        return http.Response(jsonEncode(response.body), response.status);
      }
      if (path == '/auth/refresh') {
        return http.Response(
            jsonEncode({
              'access_token': 'fictional-root-access',
              'refresh_token': 'fictional-root-refresh-at-least-32-characters',
              'session_id': 'fictional-root-session',
              'expires_in': 900,
            }),
            200);
      }
      if (path == '/me') {
        return http.Response(
            jsonEncode({
              'id': 'fictional-person-a',
              'display_name': 'Fictional Root Person',
              'access_level': 'basic',
              'capabilities': ['games:read'],
            }),
            200);
      }
      if (path == '/games') {
        return http.Response(
            jsonEncode({'items': [], 'next_cursor': null}), 200);
      }
      throw StateError('unexpected fictional endpoint');
    });
    options = AccountErasureEntryOptions(
      isOnline: () => online.value,
      connectivity: online,
      ownerFactory: (context) {
        contexts.add(context);
        final owner = AccountErasureOwner(
          store: context.store,
          session: context.session,
          transport: context.transport,
          isOnline: context.isOnline,
          connectivity: context.connectivity,
          apple: ports,
          line: ports,
          ids: owner_fixture.FixedIds(),
        );
        owners.add(owner);
        return owner;
      },
    );
  });

  tearDown(() {
    for (final owner in owners) {
      owner.dispose();
    }
    online.dispose();
  });

  BasicBootstrapApp root({bool enabled = true, Key? key}) => BasicBootstrapApp(
        key: key,
        config: AppConfig.parse(
            flavor: 'staging',
            mode: 'real',
            apiBaseUrl: 'https://example.invalid/api/v1',
            lineChannelId: '1234567890',
            googleClientId: 'fixture-ios.apps.googleusercontent.com',
            googleServerClientId: 'fixture-web.apps.googleusercontent.com'),
        store: store,
        httpClient: httpClient,
        erasureEntry: enabled ? options : null,
      );

  Future<void> entry(WidgetTester tester) async {
    await tester.tap(find.byTooltip('支援與 App 資訊'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('account-erasure-flow-entry')));
    await tester.pumpAndSettle();
  }

  Future<void> open(WidgetTester tester, String action) async {
    await tester.tap(find.byKey(ValueKey('erasure-entry-$action')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(ValueKey('confirm-erasure-entry-$action')));
    await tester.pumpAndSettle();
  }

  Future<void> action(WidgetTester tester, String name) async {
    await tester.tap(find.byKey(ValueKey('erasure-flow-$name')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(ValueKey('confirm-erasure-flow-$name')));
    await tester.pumpAndSettle();
  }

  rootTestWidgets('default has no entry and root closes injected HTTP client',
      (tester) async {
    await tester.pumpWidget(root(enabled: false));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('支援與 App 資訊'));
    await tester.pumpAndSettle();
    expect(
        find.byKey(const ValueKey('account-erasure-flow-entry')), findsNothing);
    expect(contexts, isEmpty);
    expect(requests, isEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
    expect(httpClient.closed, isTrue);
  });

  for (final provider in ['apple', 'line']) {
    rootTestWidgets(
        '$provider is explicit; boot, entry and cancelled dialog do no I/O',
        (tester) async {
      await tester.pumpWidget(root());
      await tester.pumpAndSettle();
      expect(contexts, isEmpty);
      expect(store.values.containsKey('erasure-owner:v1'), isFalse);
      await entry(tester);
      expect(find.byKey(const ValueKey('erasure-entry-google')), findsNothing);
      expect(contexts, isEmpty);
      await tester.tap(find.byKey(ValueKey('erasure-entry-$provider')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('返回'));
      await tester.pumpAndSettle();
      expect(store.values.containsKey('erasure-owner:v1'), isFalse);
      await open(tester, provider);
      expect(find.byType(AccountErasureFlowPage), findsOneWidget);
      expect(contexts, hasLength(1));
      expect(identical(contexts.single.session.store, store), isTrue);
      expect(identical(contexts.single.session.api, contexts.single.transport),
          isTrue);
      expect(contexts.single.session.terminalPurge, isNotNull);
      expect(ports.nonces, isEmpty);
      expect(requests, isEmpty);
      await action(tester, 'request');
      expect(ports.nonces, [fixture.nonce]);
      expect(erasureTransport.provider, provider);
      expect(find.textContaining(fixture.secret), findsNothing);
      expect(ports.envelopeCalls, 0);
      expect(ports.logoutCalls, 0);
    });
  }

  rootTestWidgets(
      'actual root purge clears session, caches and projection; receipt survives',
      (tester) async {
    store.values['refresh:fixture'] = 'fictional-existing-refresh';
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    expect(find.byType(BasicGamesView), findsOneWidget);
    final linking = tester
        .widget<BasicGamesView>(find.byType(BasicGamesView))
        .identityLink!;
    linking.candidateCredential = 'fictional-old-candidate';
    linking.proofCredential = 'fictional-old-proof';
    linking.safeSummary = {'display_name': 'Fictional Old Owner'};
    linking.linkedMethods = [
      LinkedLoginMethod(
          provider: 'line',
          label: 'Fictional Old Owner',
          linkedAt: DateTime.utc(2035))
    ];
    linking.linkedMethodsLoaded = true;
    linking.stage = IdentityLinkStage.proofReady;
    for (final prefix in cleanup_fixture.personalPrefixes) {
      store.values['${prefix}fictional'] = 'fictional-private';
    }
    await entry(tester);
    await open(tester, 'apple');
    final session = contexts.single.session;
    expect(session.accessToken, 'fictional-root-access');
    await action(tester, 'request');
    expect(owners.single.flow!.jobId, fixture.job);
    expect(owners.single.flow!.outcomeUnknown, isFalse);
    // A successful action deliberately does not fetch status automatically.
    await tester.tap(find.byKey(const ValueKey('erasure-flow-status')));
    await tester.pumpAndSettle();
    await action(tester, 'verify');
    expect(session.accessToken, isNull);
    expect(linking.candidateCredential, isNull);
    expect(linking.proofCredential, isNull);
    expect(linking.safeSummary, isNull);
    expect(linking.linkedMethods, isEmpty);
    expect(linking.linkedMethodsLoaded, isFalse);
    expect(linking.stage, IdentityLinkStage.idle);
    expect(store.values.containsKey('refresh:fixture'), isFalse);
    for (final prefix in cleanup_fixture.personalPrefixes) {
      expect(store.values.keys.where((key) => key.startsWith(prefix)), isEmpty);
    }
    expect(find.byType(AccountErasureFlowPage), findsOneWidget);
    expect(owners.single.flow!.jobId, fixture.job);
    await tester.tap(find.byKey(const ValueKey('erasure-flow-status')));
    await tester.pumpAndSettle();
    await action(tester, 'cancel');
    expect(erasureTransport.status, 'cancelled');
    final navigator =
        tester.state<NavigatorState>(find.byType(Navigator).first);
    navigator.popUntil((route) => route.isFirst);
    await tester.pumpAndSettle();
    expect(find.byType(BasicGamesView), findsNothing);
    expect(find.textContaining('Fictional Root Person'), findsNothing);
    expect(store.values.containsKey('erasure-owner:v1'), isTrue);
    final existingFlow = owners.single.flow;
    await entry(tester);
    await open(tester, 'resume');
    expect(owners, hasLength(1));
    expect(identical(owners.single.flow, existingFlow), isTrue);
    expect(tester.takeException(), isNull);
  });

  rootTestWidgets(
      'new login during confirmation cannot adopt captured old context',
      (tester) async {
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    await entry(tester);
    final captured = tester
        .widget<AccountErasureEntryPage>(find.byType(AccountErasureEntryPage))
        .rootContext;
    await tester.tap(find.byKey(const ValueKey('erasure-entry-apple')));
    await tester.pumpAndSettle();
    await captured.session.accept(cleanup_fixture.sessionEnvelope('other'));
    await tester.tap(find.byKey(const ValueKey('confirm-erasure-entry-apple')));
    await tester.pumpAndSettle();
    expect(contexts, isEmpty);
    expect(store.values.containsKey('erasure-owner:v1'), isFalse);
    expect(find.byType(AccountErasureFlowPage), findsNothing);
    expect(ports.nonces, isEmpty);
  });

  rootTestWidgets(
      'disposed root invalidates flow and old context even with same store',
      (tester) async {
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    await entry(tester);
    await open(tester, 'line');
    final captured = contexts.single;
    final flow = owners.single.flow!;
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    expect(captured.requireCurrent, throwsException);
    expect(flow.requireCurrent, throwsException);
    expect(httpClient.closed, isTrue);
  });

  rootTestWidgets(
      'explicit signed-out restart resumes status, never requests again',
      (tester) async {
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    await entry(tester);
    await open(tester, 'line');
    await action(tester, 'request');
    final pointer = store.values['erasure-owner:v1'];
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    final before = erasureTransport.paths.length;
    httpClient = RootHttp(httpClient.handler);
    await tester.pumpWidget(root(key: const ValueKey('restarted')));
    await tester.pumpAndSettle();
    expect(erasureTransport.paths.length, before);
    await entry(tester);
    await open(tester, 'resume');
    expect(owners.last.flow!.canRequest, isFalse);
    expect(erasureTransport.paths.skip(before), ['/account-erasure/status']);
    expect(store.values['erasure-owner:v1'], pointer);
    expect(requests.where((r) => r.url.path.contains('/auth/')), isEmpty);
  });

  rootTestWidgets(
      'uncertain request restart preserves unknown and has no replay',
      (tester) async {
    erasureTransport.loseRequest = true;
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    await entry(tester);
    await open(tester, 'apple');
    await action(tester, 'request');
    expect(owners.single.flow!.outcomeUnknown, isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    final before = erasureTransport.paths.length;
    httpClient = RootHttp(httpClient.handler);
    await tester.pumpWidget(root(key: const ValueKey('unknown-restart')));
    await tester.pumpAndSettle();
    await entry(tester);
    await open(tester, 'resume');
    expect(owners.last.flow!.outcomeUnknown, isTrue);
    expect(find.byKey(const ValueKey('erasure-flow-request')), findsNothing);
    expect(erasureTransport.paths.length, before);
  });

  rootTestWidgets('offline explicit entry does not invoke provider or HTTP',
      (tester) async {
    online.value = false;
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    await entry(tester);
    await open(tester, 'apple');
    expect(ports.nonces, isEmpty);
    expect(requests, isEmpty);
    expect(find.byType(AccountErasureFlowPage), findsOneWidget);
  });
}
