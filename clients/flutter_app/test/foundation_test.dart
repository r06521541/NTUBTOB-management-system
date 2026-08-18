import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_fictional_client/foundation.dart';

void main() {
  test('flavor parsing accepts only the three local labels', () {
    expect(FlavorConfig.parse('development').flavor, AppFlavor.development);
    expect(FlavorConfig.parse('staging').flavor, AppFlavor.staging);
    expect(FlavorConfig.parse('production').flavor, AppFlavor.production);
    expect(() => FlavorConfig.parse(''), throwsArgumentError);
    expect(() => FlavorConfig.parse('unknown'), throwsArgumentError);
  });

  test('capabilities inherit and unknown routes fail closed', () {
    final basic = CapabilityPolicy(Persona.basic);
    final officer = CapabilityPolicy(Persona.officer);
    final admin = CapabilityPolicy(Persona.admin);
    expect(basic.destinationFor('/officer/attendance'), isNull);
    expect(officer.destinationFor('/officer/attendance')?.label, '出席摘要');
    expect(officer.destinationFor('/officer/personal')?.label, '個人通知');
    expect(officer.destinationFor('/officer/broadcast')?.label, '通知廣播');
    expect(admin.destinationFor('/officer/attendance'), isNotNull);
    expect(admin.destinationFor('/admin')?.label, '系統公告');
    expect(admin.destinationFor('/unknown'), isNull);
    expect(basic.bottomDestinations.length, 4);
    expect(officer.bottomDestinations.length, 5);
    expect(admin.bottomDestinations.length, 5);
    expect(
      <CapabilityPolicy>[basic, officer, admin]
          .every((policy) => policy.bottomDestinations.length <= 5),
      isTrue,
    );
  });

  test('light and dark themes preserve requested brightness', () {
    expect(demoTheme(Brightness.light).brightness, Brightness.light);
    expect(demoTheme(Brightness.dark).brightness, Brightness.dark);
  });

  testWidgets('basic navigation switches pages and cannot reach management', (tester) async {
    await tester.pumpWidget(const DemoApp(
      persona: Persona.basic,
      flavor: FlavorConfig(AppFlavor.development),
    ));
    expect(find.text('出席摘要'), findsNothing);
    expect(find.text('管理'), findsNothing);
    await tester.tap(find.text('賽程'));
    await tester.pump();
    expect(find.byKey(const ValueKey('/schedule')), findsOneWidget);

  });

  testWidgets('officer management hub reaches its three capabilities', (tester) async {
    await tester.pumpWidget(const DemoApp(
      persona: Persona.officer,
      flavor: FlavorConfig(AppFlavor.staging),
    ));
    await tester.tap(find.text('管理'));
    await tester.pump();
    expect(find.text('出席摘要'), findsOneWidget);
    expect(find.text('個人通知'), findsOneWidget);
    expect(find.text('通知廣播'), findsOneWidget);
    expect(find.text('系統公告'), findsNothing);

    await tester.tap(find.text('出席摘要'));
    await tester.pumpAndSettle();
    expect(find.text('本週回覆率 80%'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('個人通知'));
    await tester.pumpAndSettle();
    expect(find.text('fictional 個人通知預覽'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('通知廣播'));
    await tester.pumpAndSettle();
    expect(find.text('fictional 通知廣播預覽'), findsOneWidget);
  });

  testWidgets('admin inherits officer hub and reaches announcement', (tester) async {
    await tester.pumpWidget(const DemoApp(
      persona: Persona.admin,
      flavor: FlavorConfig(AppFlavor.production),
    ));
    await tester.tap(find.text('管理'));
    await tester.pump();
    expect(find.text('出席摘要'), findsOneWidget);
    expect(find.text('個人通知'), findsOneWidget);
    expect(find.text('通知廣播'), findsOneWidget);
    expect(find.text('系統公告'), findsOneWidget);
    await tester.tap(find.text('系統公告'));
    await tester.pumpAndSettle();
    expect(find.text('系統公告預覽'), findsOneWidget);
  });

  for (final entry in <LoadState, String>{
    LoadState.loading: '正在載入，請稍候',
    LoadState.empty: '目前沒有內容',
    LoadState.error: '暫時無法顯示',
    LoadState.offline: '目前為離線唯讀模式',
  }.entries) {
    testWidgets('${entry.key.name} has identifiable UI', (tester) async {
      await tester.pumpWidget(MaterialApp(home: StatePanel(
        state: entry.key,
        lastSyncedAt: DateTime.utc(2026, 1, 2, 3, 4),
      )));
      expect(find.text(entry.value), findsOneWidget);
      expect(find.byType(Semantics), findsWidgets);
      if (entry.key == LoadState.loading) {
        expect(find.byType(CircularProgressIndicator), findsOneWidget);
      }
    });
  }

  testWidgets('offline UI displays deterministic last sync time', (tester) async {
    await tester.pumpWidget(MaterialApp(home: StatePanel(
      state: LoadState.offline,
      lastSyncedAt: DateTime.utc(2026, 1, 2, 3, 4),
    )));
    expect(find.text('最後同步：2026-01-02 03:04 UTC'), findsOneWidget);
  });

  test('fake repository is deterministic and offline read-only', () async {
    final repo = InMemoryFakeApiRepository(lastSyncedAt: DateTime.utc(2026, 1, 2));
    final snapshot = await repo.readSnapshot();
    expect(snapshot.lastSyncedAt, DateTime.utc(2026, 1, 2));
    expect(snapshot.fixtures.account, '示範會員');
    expect(snapshot.fixtures.schedule, hasLength(2));
    expect(snapshot.fixtures.replies, hasLength(2));
    expect(snapshot.fixtures.notifications, hasLength(1));
    expect(snapshot.fixtures.officerSummary, '本週回覆率 80%');
    expect(snapshot.fixtures.adminAnnouncement, '系統公告預覽');
    expect(repo.submitOfflineMutation(), throwsStateError);
  });

  test('fake push records deterministic in-memory events', () {
    final push = FakePushRepository();
    push.record(const FictionalPushEvent('event-1', '示範通知'));
    expect(push.events.single.id, 'event-1');
    expect(push.events.single.message, '示範通知');
    expect(() => push.events.add(const FictionalPushEvent('event-2', '不可寫入')), throwsUnsupportedError);
  });
}
