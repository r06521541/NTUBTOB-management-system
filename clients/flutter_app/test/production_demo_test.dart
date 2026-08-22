import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/foundation.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/main.dart' as entrypoint;
import 'package:ntubtob_portal/notification_center.dart';
import 'package:ntubtob_portal/officer_prereview.dart';
import 'package:ntubtob_portal/production_demo.dart';

void main() {
  AppConfig config(ClientMode mode) => AppConfig.parse(
        flavor: mode == ClientMode.fake ? 'development' : 'staging',
        mode: mode.name,
        apiBaseUrl: mode == ClientMode.real ? 'https://example.invalid' : '',
        lineChannelId: mode == ClientMode.real ? '123456' : '',
      );

  Future<void> pumpDemo(
    WidgetTester tester, {
    ProductionDemoProbe? probe,
  }) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProductionDemoApp(
        flavor: const FlavorConfig(AppFlavor.development),
        probe: probe,
      ),
    );
    await tester.pumpAndSettle();
  }

  test('fake composition selects production demo and real stays bootstrap', () {
    final fake = entrypoint.composeRoot(config(ClientMode.fake));
    final real = entrypoint.composeRoot(config(ClientMode.real));

    expect(fake, isA<ProductionDemoApp>());
    expect(fake, isA<DemoApp>());
    expect(real, isA<BasicBootstrapApp>());
  });

  testWidgets('boots visibly fictional production Basic surface', (
    tester,
  ) async {
    await pumpDemo(tester);

    expect(
      find.byKey(const ValueKey('production-demo-fictional-banner')),
      findsOneWidget,
    );
    expect(find.text('虛構展示資料・不使用帳號・不連線'), findsOneWidget);
    expect(find.byType(BasicGamesView), findsOneWidget);
    expect(find.byKey(const ValueKey('game-game_901')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('account-data-status-entry')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('support-app-info-entry')), findsOneWidget);
    expect(find.byKey(const ValueKey('management-report-entry')), findsNothing);
  });

  testWidgets(
    'scenario controls cover Officer offline empty and error states',
    (tester) async {
      await pumpDemo(tester);

      await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('management-report-entry')),
        findsOneWidget,
      );

      await tester.tap(find.byKey(const ValueKey('demo-connectivity-offline')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('offline-read-only')), findsOneWidget);
      expect(
        tester
            .widget<ListTile>(find.byKey(const ValueKey('game-game_901')))
            .onTap,
        isNull,
      );

      await tester.tap(find.byKey(const ValueKey('demo-data-empty')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('games-empty')), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('demo-data-error')));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('production-demo-error')),
        findsOneWidget,
      );
      expect(find.byType(AuthStatePanel), findsOneWidget);
    },
  );

  testWidgets('production detail reads deterministic adapters only', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);

    await tester.tap(find.byKey(const ValueKey('game-game_901')));
    await tester.pumpAndSettle();

    expect(find.byType(GameDetailPage), findsOneWidget);
    expect(find.byKey(const ValueKey('game-detail-metadata')), findsOneWidget);
    expect(find.byType(ChoiceChip), findsNWidgets(5));
    expect(probe.gameReads, 1);
    expect(probe.attendanceReads, 1);
    expect(probe.unexpectedTransportCalls, 0);

    await tester.tap(find.byKey(const ValueKey('reply-undecided')));
    await tester.tap(find.text('送出回覆'));
    await tester.pumpAndSettle();
    expect(probe.replyMutations, 1);
    expect(probe.attendanceReads, 2);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets('production account surface is reachable without transport', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);

    await tester.tap(find.byKey(const ValueKey('account-data-status-entry')));
    await tester.pumpAndSettle();

    expect(find.byType(AccountDataStatusPage), findsOneWidget);
    expect(
      find.byKey(const ValueKey('account-data-provenance')),
      findsOneWidget,
    );
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets(
      'production demo opens loaded notification detail without transport', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);
    await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
    await tester.pumpAndSettle();

    expect(find.text('通知中心 (1)'), findsOneWidget);
    await tester.tap(find.text('虛構賽事提醒'));
    await tester.pumpAndSettle();
    expect(find.byType(NotificationDetailPage), findsOneWidget);
    expect(find.text('這是展示用的未讀通知。'), findsOneWidget);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets('production demo opens the shared support page without transport', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);

    await tester.tap(find.byKey(const ValueKey('support-app-info-entry')));
    await tester.pumpAndSettle();

    expect(find.text('支援與 App 資訊'), findsOneWidget);
    expect(find.byKey(const ValueKey('app-version-metadata')), findsOneWidget);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets('production demo resolves an authorized game destination', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);
    await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
    await tester.pumpAndSettle();

    await tester.tap(find.text('虛構場地異動'));
    await tester.pumpAndSettle();

    expect(find.byType(GameDetailPage), findsOneWidget);
    expect(find.byKey(const ValueKey('game-detail-metadata')), findsOneWidget);
    expect(probe.gameReads, 1);
    expect(probe.attendanceReads, 1);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets('Officer reaches online production report with fake data only', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);

    await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('management-report-entry')));
    await tester.pumpAndSettle();
    expect(find.byType(CanonicalManagementReportsPage), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('report-game-game_901')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('officer-report-ready')), findsOneWidget);
    expect(find.text('虛構出席隊員'), findsOneWidget);
    expect(probe.reportReads, 1);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets('Officer offline report uses preloaded in-memory cache', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);

    await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
    await tester.tap(find.byKey(const ValueKey('demo-connectivity-offline')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('management-report-entry')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('report-game-game_901')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('officer-report-offlineCached')),
      findsOneWidget,
    );
    expect(find.text('目前為離線快取，僅供讀取'), findsOneWidget);
    expect(probe.reportReads, 0);
    expect(probe.unexpectedTransportCalls, 0);
  });
}
