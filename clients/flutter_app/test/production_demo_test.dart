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
        googleClientId: mode == ClientMode.real
            ? 'fixture-ios.apps.googleusercontent.com'
            : '',
        googleServerClientId: mode == ClientMode.real
            ? 'fixture-web.apps.googleusercontent.com'
            : '',
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

  Future<void> openServerPublishDraft(WidgetTester tester) async {
    await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('demo-server-publish-flow-entry')),
    );
    await tester.pumpAndSettle();
    expect(find.byType(CanonicalManagementReportsPage), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('report-game-game_901')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('unanswered-notification-draft-entry')),
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
    expect(
      find.byKey(const ValueKey('support-app-info-entry')),
      findsOneWidget,
    );
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
    final initialAttendanceReads = probe.attendanceReads;

    await tester.tap(find.byKey(const ValueKey('game-game_901')));
    await tester.pumpAndSettle();

    expect(find.byType(GameDetailPage), findsOneWidget);
    expect(find.byKey(const ValueKey('game-detail-metadata')), findsOneWidget);
    expect(find.byType(ChoiceChip), findsNWidgets(5));
    expect(probe.gameReads, 1);
    expect(probe.attendanceReads, initialAttendanceReads + 1);
    expect(probe.unexpectedTransportCalls, 0);

    await tester.tap(find.byKey(const ValueKey('reply-undecided')));
    await tester.tap(find.text('送出回覆'));
    await tester.pumpAndSettle();
    expect(probe.replyMutations, 1);
    expect(probe.attendanceReads, initialAttendanceReads + 2);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets('production demo composes bounded member action scenarios', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);
    expect(
      find.byKey(const ValueKey('action-home-actionable')),
      findsOneWidget,
    );
    expect(find.textContaining('未來最多 5 場'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('demo-data-resolved')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('action-home-resolved')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('demo-data-action-error')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('action-home-retryableError')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey('demo-data-populated')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('demo-connectivity-offline')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('action-home-partialUnknown')),
      findsOneWidget,
    );
    expect(find.textContaining('未知不列為待處理'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('demo-data-empty')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('action-home-empty')), findsOneWidget);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets(
    'schedule discovery groups, filters, and keeps search on return',
    (tester) async {
      await pumpDemo(tester);

      await tester.tap(find.byKey(const ValueKey('schedule-discovery-entry')));
      await tester.pumpAndSettle();

      expect(find.byType(ScheduleDiscoveryPage), findsOneWidget);
      expect(
        find.byKey(const ValueKey('schedule-game-game_901')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('schedule-game-game_903')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('schedule-date-2026-10-03T00:00:00.000')),
        findsOneWidget,
      );

      await tester.tap(
        find.byKey(const ValueKey('schedule-filter-withLocation')),
      );
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('schedule-game-game_901')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('schedule-game-game_903')),
        findsNothing,
      );
      await tester.tap(find.byKey(const ValueKey('schedule-filter-all')));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const ValueKey('schedule-search')),
        '猛虎',
      );
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('schedule-game-game_903')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('schedule-game-game_901')),
        findsNothing,
      );

      await tester.tap(find.byKey(const ValueKey('schedule-game-game_903')));
      await tester.pumpAndSettle();
      expect(find.byType(GameDetailPage), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<TextField>(find.byKey(const ValueKey('schedule-search')))
            .controller!
            .text,
        '猛虎',
      );

      await tester.enterText(
        find.byKey(const ValueKey('schedule-search')),
        '不存在的球隊',
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('schedule-no-match')), findsOneWidget);
    },
  );

  testWidgets(
    'schedule discovery distinguishes empty and offline cached views',
    (tester) async {
      final probe = ProductionDemoProbe();
      await pumpDemo(tester, probe: probe);

      await tester.tap(find.byKey(const ValueKey('demo-data-empty')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('schedule-discovery-entry')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('schedule-empty')), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('demo-data-populated')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('demo-connectivity-offline')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('schedule-discovery-entry')));
      await tester.pumpAndSettle();
      expect(find.text('離線唯讀賽程'), findsOneWidget);
      final gameReads = probe.gameReads;
      final attendanceReads = probe.attendanceReads;
      final replyMutations = probe.replyMutations;
      await tester.tap(find.byKey(const ValueKey('schedule-game-game_901')));
      await tester.pumpAndSettle();
      expect(find.byType(CachedGameDetailPage), findsOneWidget);
      expect(probe.gameReads, gameReads);
      expect(probe.attendanceReads, attendanceReads);
      expect(probe.replyMutations, replyMutations);
      expect(probe.unexpectedTransportCalls, 0);
    },
  );

  testWidgets(
    'production schedule demo covers month week and empty-day states',
    (tester) async {
      await pumpDemo(tester);

      await tester.tap(find.byKey(const ValueKey('schedule-discovery-entry')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('月'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('schedule-next-period')));
      await tester.pumpAndSettle();

      expect(find.text('2026 年 10 月'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('schedule-day-2026-10-03')));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView).first, const Offset(0, -900));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('schedule-game-game_903')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('schedule-game-game_904')),
        findsOneWidget,
      );

      await tester.drag(find.byType(ListView).first, const Offset(0, 900));
      await tester.pumpAndSettle();
      await tester.tap(find.text('週'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('schedule-next-period')));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('schedule-game-game_905')),
        findsOneWidget,
      );

      await tester.tap(find.text('月'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.byKey(const ValueKey('schedule-day-2026-10-04')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('schedule-day-2026-10-04')));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView).first, const Offset(0, -900));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('schedule-day-no-games')),
        findsOneWidget,
      );

      await tester.drag(find.byType(ListView).first, const Offset(0, 1400));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('schedule-search')),
        'no production demo match',
      );
      await tester.ensureVisible(
        find.byKey(const ValueKey('schedule-day-2026-10-03')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('schedule-day-2026-10-03')));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView).first, const Offset(0, -900));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('schedule-day-no-match')),
        findsOneWidget,
      );
    },
  );

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
    'demo account link and recovery are explicit fictional journeys',
    (tester) async {
      final probe = ProductionDemoProbe();
      await pumpDemo(tester, probe: probe);
      await tester.tap(find.byKey(const ValueKey('demo-account-link')));
      await tester.pumpAndSettle();
      expect(find.text('虛構帳號管理'), findsOneWidget);
      expect(find.text('LINE'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('identity-link-begin-google')),
        findsOneWidget,
      );
      expect(
        find.textContaining(RegExp(r'已連結 2026年8月20日 \d{2}:00')),
        findsOneWidget,
      );
      expect(find.textContaining('Thursday'), findsNothing);
      expect(find.textContaining('August'), findsNothing);
      expect(find.textContaining('.000'), findsNothing);
      await tester.tap(
        find.byKey(const ValueKey('identity-link-begin-google')),
      );
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('identity-link-proof-line')));
      await tester.pump();
      expect(find.textContaining('確認將 Google 加入'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('identity-link-confirm')));
      await tester.pump();
      expect(
        find.byKey(const ValueKey('identity-link-completed')),
        findsOneWidget,
      );
      await tester.pageBack();
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('demo-account-recovery')));
      await tester.pumpAndSettle();
      expect(find.text('兩步驟安全追認'), findsOneWidget);
      await tester.tap(
        find.byKey(const ValueKey('identity-link-begin-google')),
      );
      await tester.pump();
      expect(find.byKey(const ValueKey('identity-link-confirm')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('identity-link-proof-line')));
      await tester.pump();
      expect(
        find.byKey(const ValueKey('identity-link-confirm')),
        findsOneWidget,
      );
      expect(probe.unexpectedTransportCalls, 0);
    },
  );

  testWidgets(
    'Officer notification draft uses authoritative fake preview then confirms',
    (tester) async {
      final probe = ProductionDemoProbe();
      await pumpDemo(tester, probe: probe);
      await openServerPublishDraft(tester);
      expect(find.text('收件人 1/1'), findsOneWidget);
      expect(find.textContaining('虛構校友隊 vs 範例友隊'), findsOneWidget);
      expect(find.textContaining('game_901'), findsNothing);
      await tester.tap(
        find.byKey(const ValueKey('notification-draft-server-preview')),
      );
      await tester.pumpAndSettle();
      expect(find.text('伺服器確認收件人：1 人'), findsOneWidget);
      expect(probe.previewDrafts.single['audience']['person_ids'], [
        'fictional-unanswered',
      ]);
      expect(probe.previewRevisions.single, hasLength(64));
      expect(probe.confirmKeys, isEmpty);

      final confirmation = find.byKey(
        const ValueKey('notification-draft-server-confirmation'),
      );
      await tester.enterText(confirmation, 'PUBLISH 0');
      await tester.pump();
      expect(probe.confirmKeys, isEmpty);
      await tester.enterText(confirmation, 'PUBLISH 1');
      await tester.pump();
      await tester.tap(
        find.byKey(const ValueKey('notification-draft-server-confirm')),
      );
      await tester.pumpAndSettle();
      expect(find.text('App 內通知已保存；外部推播仍在 outbox，尚未保證送達'), findsOneWidget);
      expect(probe.confirmDrafts, hasLength(1));
      expect(
        probe.confirmPreviews.single['revision'],
        probe.previewRevisions.single,
      );
      expect(probe.confirmKeys.single, hasLength(43));
      expect(probe.unexpectedTransportCalls, 0);
    },
  );

  testWidgets('changing selected recipients invalidates a stale server preview',
      (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);
    await openServerPublishDraft(tester);
    await tester.tap(
      find.byKey(const ValueKey('notification-draft-server-preview')),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('notification-draft-server-confirmation')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey('notification-recipient-fictional-unanswered')),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('notification-draft-server-confirmation')),
      findsNothing,
    );
    expect(probe.confirmDrafts, isEmpty);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets('offline publish flow stays local-only with zero fake calls', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);
    await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('demo-connectivity-offline')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('demo-server-publish-flow-entry')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('report-game-game_901')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('unanswered-notification-draft-entry')),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('notification-draft-offline')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('notification-draft-server-preview')),
      findsNothing,
    );
    expect(probe.previewDrafts, isEmpty);
    expect(probe.confirmDrafts, isEmpty);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets(
    'publish demo exposes a deterministic preview failure',
    (tester) async {
      final probe = ProductionDemoProbe();
      await pumpDemo(tester, probe: probe);
      await tester.tap(
        find.byKey(const ValueKey('demo-publish-preview-error')),
      );
      await tester.pumpAndSettle();
      await openServerPublishDraft(tester);
      await tester.tap(
        find.byKey(const ValueKey('notification-draft-server-preview')),
      );
      await tester.pumpAndSettle();
      expect(find.text('伺服器預覽失敗；未發布通知'), findsOneWidget);
      expect(probe.confirmDrafts, isEmpty);
      expect(probe.unexpectedTransportCalls, 0);
    },
  );

  testWidgets('publish demo exposes a deterministic confirm failure', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);
    await tester.tap(
      find.byKey(const ValueKey('demo-publish-confirm-error')),
    );
    await tester.pumpAndSettle();
    await openServerPublishDraft(tester);
    await tester.tap(
      find.byKey(const ValueKey('notification-draft-server-preview')),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('notification-draft-server-confirmation')),
      'PUBLISH 1',
    );
    await tester.pump();
    await tester.tap(
      find.byKey(const ValueKey('notification-draft-server-confirm')),
    );
    await tester.pumpAndSettle();
    expect(find.text('發布失敗；請重新取得伺服器預覽'), findsOneWidget);
    expect(probe.confirmDrafts, hasLength(1));
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets(
    'offline notification center reads the seeded principal cache for Basic and Officer',
    (tester) async {
      final probe = ProductionDemoProbe();
      await pumpDemo(tester, probe: probe);

      await tester.tap(find.byKey(const ValueKey('demo-connectivity-offline')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
      await tester.pumpAndSettle();
      expect(find.text('虛構賽事提醒'), findsOneWidget);
      expect(find.textContaining('離線模式：顯示上次同步內容'), findsOneWidget);
      expect(find.text('沒有離線通知'), findsNothing);
      await tester.pageBack();
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
      await tester.pumpAndSettle();
      expect(find.text('虛構賽事提醒'), findsOneWidget);
      expect(find.text('沒有離線通知'), findsNothing);
      expect(probe.unexpectedTransportCalls, 0);
    },
  );

  testWidgets('notification demo selects an explicit empty scenario', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);

    await tester.tap(find.byKey(const ValueKey('demo-notifications-empty')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
    await tester.pumpAndSettle();

    expect(find.text('目前沒有通知'), findsOneWidget);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets('notification demo selects a retryable error scenario', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);

    await tester.tap(find.byKey(const ValueKey('demo-notifications-error')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
    await tester.pumpAndSettle();
    expect(find.text('通知載入失敗'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('notification-refresh')));
    await tester.pumpAndSettle();
    expect(find.text('通知載入失敗'), findsOneWidget);
    expect(probe.unexpectedTransportCalls, 0);
  });

  testWidgets(
    'production demo opens loaded notification detail without transport',
    (tester) async {
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
    },
  );

  testWidgets(
    'production demo opens the shared support page without transport',
    (tester) async {
      final probe = ProductionDemoProbe();
      await pumpDemo(tester, probe: probe);

      await tester.tap(find.byKey(const ValueKey('support-app-info-entry')));
      await tester.pumpAndSettle();

      expect(find.text('支援與 App 資訊'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('app-version-metadata')),
        findsOneWidget,
      );
      expect(probe.unexpectedTransportCalls, 0);
    },
  );

  testWidgets('production demo resolves an authorized game destination', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);
    final initialAttendanceReads = probe.attendanceReads;
    await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
    await tester.pumpAndSettle();

    expect(find.text('虛構場地異動'), findsNothing);
    await tester.tap(find.text('載入更多'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('虛構場地異動'));
    await tester.pumpAndSettle();

    expect(find.byType(GameDetailPage), findsOneWidget);
    expect(find.byKey(const ValueKey('game-detail-metadata')), findsOneWidget);
    expect(probe.gameReads, 1);
    expect(probe.attendanceReads, initialAttendanceReads + 1);
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

  testWidgets(
    'Officer report opens the session-local Lineup Lab only from attendees',
    (tester) async {
      final probe = ProductionDemoProbe();
      await pumpDemo(tester, probe: probe);
      await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('management-report-entry')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('report-game-game_901')));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('attendance-insights')), findsOneWidget);
      expect(find.textContaining('可出席 1 人'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('lineup-lab-entry')));
      await tester.pumpAndSettle();
      expect(find.text('這是本次開啟期間的規劃草稿，不是正式提交，也不會儲存或分享。'), findsOneWidget);
      expect(find.byKey(const ValueKey('lineup-warning')), findsOneWidget);
      expect(find.text('先發 0/9・缺 9 人・候補／未安排 1 人・尚未回覆 1 人'), findsOneWidget);
      await tester.tap(find.text('細排'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('lineup-empty-slot-9')), findsOneWidget);
      expect(find.byKey(const ValueKey('lineup-empty-slot-1')), findsOneWidget);
      expect(find.text('虛構不出席隊員'), findsNothing);
      expect(probe.unexpectedTransportCalls, 0);
    },
  );

  testWidgets('production Lineup Lab composes ten-player empty fine draft', (
    tester,
  ) async {
    final probe = ProductionDemoProbe();
    await pumpDemo(tester, probe: probe);
    await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('management-report-entry')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('report-game-game_902')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-lab-entry')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('lineup-warning')), findsOneWidget);
    expect(find.text('先發 0/9・缺 9 人・候補／未安排 10 人・尚未回覆 0 人'), findsOneWidget);
    await tester.tap(find.text('細排'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('候補／未安排 10'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('lineup-reserve-fictional-ready-9')),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('lineup-reserve-fictional-ready-9')),
      findsOneWidget,
    );
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
    await tester.tap(find.byKey(const ValueKey('lineup-lab-entry')));
    await tester.pumpAndSettle();
    expect(find.textContaining('離線唯讀來源可能過期'), findsOneWidget);
    expect(find.byKey(const ValueKey('lineup-warning')), findsOneWidget);
    expect(probe.reportReads, 0);
    expect(probe.unexpectedTransportCalls, 0);
  });
}
