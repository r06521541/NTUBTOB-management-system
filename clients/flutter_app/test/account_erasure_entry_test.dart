import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_entry.dart';
import 'package:ntubtob_portal/account_erasure_flow.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/local_preferences.dart';
import 'package:ntubtob_portal/support_app_info.dart';

import 'account_erasure_action_test.dart' as fixture;
import 'account_erasure_owner_test.dart' as owner_fixture;
import 'account_erasure_provider_test.dart' as provider_fixture;

class OfflineFlow extends ChangeNotifier implements AccountErasureFlowPort {
  int calls = 0;
  @override
  Listenable get changes => this;
  @override
  bool get online => false;
  @override
  int get generation => 0;
  @override
  bool get canRequest => true;
  @override
  bool get outcomeUnknown => false;
  @override
  String? get jobId => null;
  @override
  void requireCurrent() {}
  @override
  Future<Map<String, dynamic>?> readStatus() async {
    calls++;
    return null;
  }

  @override
  Future<void> request({required bool confirmed}) async {
    calls++;
  }

  @override
  Future<void> verify({required bool confirmed}) async {
    calls++;
  }

  @override
  Future<void> cancel({required bool confirmed}) async {
    calls++;
  }

  @override
  Future<void> recoverReceipt({required bool confirmed}) async {
    calls++;
  }
}

void main() {
  for (final enabled in [false, true]) {
    test(
        'captured context forwards only explicit fresh Google, enabled=$enabled',
        () async {
      final store = owner_fixture.OwnerStore();
      final transport = owner_fixture.OwnerTransport();
      final ports = provider_fixture.ProofPorts();
      final google = enabled ? provider_fixture.GoogleProofPort(ports) : null;
      final online = ValueNotifier(true);
      addTearDown(online.dispose);
      final options = AccountErasureEntryOptions(
        isOnline: () => online.value,
        connectivity: online,
        google: google,
      );
      final session = SessionController(
          transport, store, 'fixture', SecureIds(),
          terminalPurge: () async {});
      final context = AccountErasureRootContext(
        store: store,
        session: session,
        transport: transport,
        line: ports,
        apple: ports,
        google: options.google,
        options: options,
        requireCurrent: () {},
      );
      final owner = context.createOwner();
      addTearDown(owner.dispose);
      expect(identical(context.google, google), isTrue);
      expect(store.reads, 0);
      expect(store.writes, 0);
      expect(ports.nonces, isEmpty);
      expect(transport.paths, isEmpty);
      if (enabled) {
        final flow = await owner.start(provider: 'google', confirmed: true);
        expect(ports.nonces, isEmpty);
        expect(transport.paths, isEmpty);
        await flow.request(confirmed: true);
        expect(ports.nonces, [fixture.nonce]);
        expect(transport.provider, 'google');
      } else {
        await expectLater(
            owner.start(provider: 'google', confirmed: true), throwsException);
        expect(store.reads, 0);
        expect(store.writes, 0);
        expect(ports.nonces, isEmpty);
        expect(transport.paths, isEmpty);
      }
      expect(ports.logoutCalls, 0);
      expect(ports.envelopeCalls, 0);
    });
  }

  test('stale captured context rejects before constructing a Google owner', () {
    final store = owner_fixture.OwnerStore();
    final transport = owner_fixture.OwnerTransport();
    final ports = provider_fixture.ProofPorts();
    final online = ValueNotifier(true);
    addTearDown(online.dispose);
    final google = provider_fixture.GoogleProofPort(ports);
    final context = AccountErasureRootContext(
      store: store,
      session: SessionController(transport, store, 'fixture', SecureIds(),
          terminalPurge: () async {}),
      transport: transport,
      line: ports,
      apple: null,
      google: google,
      options: AccountErasureEntryOptions(
        isOnline: () => online.value,
        connectivity: online,
        google: google,
      ),
      requireCurrent: () => throw StateError('fictional stale context'),
    );
    expect(context.createOwner, throwsStateError);
    expect(store.reads, 0);
    expect(store.writes, 0);
    expect(ports.nonces, isEmpty);
    expect(transport.paths, isEmpty);
  });

  for (final onboarded in [false, true]) {
    testWidgets(
        'receipt entry reachable without business login, onboarding=$onboarded',
        (tester) async {
      final store = MemoryStore();
      await store.write('installation:v1', 'fictional-install');
      if (onboarded) {
        await LocalPreferences(store, 'fictional-install').completeOnboarding();
      }
      final online = ValueNotifier(false);
      addTearDown(online.dispose);
      await tester.pumpWidget(BasicBootstrapApp(
        config: AppConfig.parse(
            flavor: 'staging',
            mode: 'real',
            apiBaseUrl: 'https://example.invalid/api/v1',
            lineChannelId: '1234567890',
            googleClientId: 'fixture-ios.apps.googleusercontent.com',
            googleServerClientId: 'fixture-web.apps.googleusercontent.com'),
        store: store,
        erasureEntry: AccountErasureEntryOptions(
          isOnline: () => online.value,
          connectivity: online,
        ),
      ));
      await tester.pumpAndSettle();
      final before = Map<String, String>.of(store.values);
      await tester.tap(find.byTooltip('支援與 App 資訊'));
      await tester.pumpAndSettle();
      await tester
          .tap(find.byKey(const ValueKey('account-erasure-flow-entry')));
      await tester.pumpAndSettle();
      expect(find.byType(AccountErasureEntryPage), findsOneWidget);
      expect(find.byType(AccountErasureFlowPage), findsNothing);
      expect(store.values, before);
      expect(tester.takeException(), isNull);
    });
  }
  testWidgets(
      'explicit erasure entry opens flow without contacting server offline',
      (tester) async {
    final flow = OfflineFlow();
    addTearDown(flow.dispose);
    await tester.pumpWidget(MaterialApp(
      home: SupportAppInfoPage(
        erasureEntryBuilder: (_) => AccountErasureFlowPage(port: flow),
      ),
    ));
    expect(find.textContaining('既有球隊聯絡管道'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('account-erasure-flow-entry')));
    await tester.pumpAndSettle();
    expect(find.byType(AccountErasureFlowPage), findsOneWidget);
    expect(flow.calls, 0);
  });
}
