import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/officer_prereview.dart';

class ReportTransport implements ApiTransport {
  final calls = <(String, String)>[];
  ApiResponse response = ApiResponse(200, {
    'game_id': 'game_44',
    'generated_at': '2026-08-18T12:00:00Z',
    'observation': {
      'history_games': 8,
      'history_limit': 12,
      'minimum_response_rate': 60,
    },
    'attending': [
      {
        'person_id': 'person_1',
        'display_name': '已出席',
        'reply': 'attending',
        'member_number': 18,
      }
    ],
    'not_attending': [
      {'person_id': 'person_3', 'display_name': '不出席', 'reply': 'not_attending'}
    ],
    'not_yet_replied': [
      {
        'person_id': 'person_2',
        'display_name': '尚未回覆',
        'observed_replies': 7,
        'observed_games': 8,
        'response_rate': 88,
        'participation_rate': 63,
        'nonparticipation_rate': 25,
      }
    ],
  });

  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    calls.add((method, path));
    return response;
  }
}

Map<String, dynamic> reportError(String code, {bool retryable = false}) => {
      'error': {
        'code': code,
        'message': 'safe',
        'request_id': 'request',
        'retryable': retryable,
        'retry_after_seconds': null,
        'field_errors': [],
      }
    };

class FailingWriteStore extends MemoryStore {
  bool failNextWrite = false;

  @override
  Future<void> write(String key, String value) async {
    if (failNextWrite) {
      failNextWrite = false;
      throw const NetworkException();
    }
    await super.write(key, value);
  }
}

Future<BasicApi> reportApi(ReportTransport transport) async {
  final store = MemoryStore();
  final session = SessionController(transport, store, 'install', SecureIds());
  await session.accept(const SessionEnvelope(
    accessToken: 'access',
    refreshToken: 'refresh-token-with-at-least-32-characters',
    sessionId: 'session',
    expiresIn: 900,
  ));
  return BasicApi(session, store, 'install', SecureIds());
}

SingleGameReportUiModel reportWithId(String id) {
  final source = DeterministicFakeOfficerReportRepository.fictionalReport;
  return SingleGameReportUiModel(
    gameId: id,
    gameLabel: '賽事 $id',
    generatedAt: source.generatedAt,
    historyGames: source.historyGames,
    historyLimit: source.historyLimit,
    minimumResponseRate: source.minimumResponseRate,
    attending: source.attending,
    notAttending: source.notAttending,
    notYetReplied: source.notYetReplied,
  );
}

SingleGameReportUiModel emptyReport() => SingleGameReportUiModel(
      gameId: 'empty',
      gameLabel: '空白賽事',
      generatedAt: DateTime.utc(2026),
      historyGames: 0,
      historyLimit: 12,
      minimumResponseRate: 60,
      attending: const [],
      notAttending: const [],
      notYetReplied: const [],
    );

SingleGameReportUiModel lineupReport({
  String gameId = 'lineup-quality',
  int attending = 10,
  int unanswered = 1,
}) =>
    SingleGameReportUiModel(
      gameId: gameId,
      gameLabel: 'Lineup quality',
      generatedAt: DateTime.utc(2026),
      historyGames: 1,
      historyLimit: 12,
      minimumResponseRate: 60,
      attending: List.generate(
        attending,
        (index) => ReportParticipantUiModel(
          id: 'quality-$index',
          displayName: 'Quality $index',
          memberNumber: index + 1,
          reply: index == attending - 1
              ? AttendanceReply.leavingEarly
              : AttendanceReply.attending,
        ),
      ),
      notAttending: const [],
      notYetReplied: List.generate(
        unanswered,
        (index) => NotYetRepliedUiModel(
          id: 'unanswered-$index',
          displayName: 'Unanswered $index',
          observedReplies: 0,
          observedGames: 1,
          responseRate: 0,
          participationRate: 0,
          nonparticipationRate: 0,
        ),
      ),
    );

SingleGameReportUiModel largeBoundedReport() {
  final source = DeterministicFakeOfficerReportRepository.fictionalReport;
  return SingleGameReportUiModel(
    gameId: 'large',
    gameLabel: '大型報表',
    generatedAt: source.generatedAt,
    historyGames: source.historyGames,
    historyLimit: source.historyLimit,
    minimumResponseRate: source.minimumResponseRate,
    attending: List.generate(
      200,
      (index) => ReportParticipantUiModel(
        id: 'person-$index',
        displayName: '員' * 120,
      ),
    ),
    notAttending: const [],
    notYetReplied: const [],
  );
}

OfficerReportController controllerFor({
  OfficerReportPresentationPort? repository,
  InMemoryPrincipalOfficerReportCache? cache,
  LineupSummaryCopyPort? copyPort,
}) =>
    OfficerReportController(
      repository: repository ?? DeterministicFakeOfficerReportRepository(),
      cache: cache ?? InMemoryPrincipalOfficerReportCache(),
      lineupSummaryCopyPort: copyPort ?? RecordingLineupCopyPort(),
    );

Future<OfficerReportController> pumpLineupLab(
  WidgetTester tester,
  SingleGameReportUiModel report, {
  bool offline = false,
  bool fine = true,
  LineupSummaryCopyPort? copyPort,
}) async {
  tester.view.physicalSize = const Size(1600, 2200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final controller = controllerFor(copyPort: copyPort);
  await controller.applyFreshPrincipal(
    principalId: 'officer',
    reportReadGrant: const ManagementReportReadGrant.granted(),
  );
  controller
    ..report = report
    ..state = offline
        ? OfficerReportViewState.offlineCached
        : OfficerReportViewState.ready;
  await tester.pumpWidget(
    MaterialApp(home: OfficerReportPanel(controller: controller)),
  );
  await tester.tap(find.byKey(const ValueKey('lineup-lab-entry')));
  await tester.pumpAndSettle();
  if (fine) {
    await tester.tap(find.text('細排'));
    await tester.pumpAndSettle();
  }
  return controller;
}

class RecordingLineupCopyPort implements LineupSummaryCopyPort {
  final summaries = <String>[];

  @override
  Future<void> copy(String summary) async => summaries.add(summary);
}

class PreviewingPublisher implements NotificationPublishingClient {
  final previews = <Map<String, dynamic>>[];
  final confirms = <Map<String, dynamic>>[];

  @override
  Future<Map<String, dynamic>> preview(Map<String, dynamic> draft) async {
    previews.add(draft);
    return {
      'recipient_count': 2,
      'revision': 'a' * 64,
      'confirmation_text': 'PUBLISH 2',
    };
  }

  @override
  Future<Map<String, dynamic>> confirm(
    Map<String, dynamic> draft,
    Map<String, dynamic> preview,
    String key,
  ) async {
    confirms.add({'draft': draft, 'preview': preview, 'key': key});
    return {'notification_id': 'notification_1', 'recipient_count': 2};
  }
}

class DelayedPreviewPublisher extends PreviewingPublisher {
  final response = Completer<Map<String, dynamic>>();

  @override
  Future<Map<String, dynamic>> preview(Map<String, dynamic> draft) {
    previews.add(draft);
    return response.future;
  }
}

void main() {
  test(
      'notification draft derives exact unanswered recipients and resets per game',
      () {
    final controller = controllerFor();
    final first = controller.notificationDraftFor(
      lineupReport(gameId: 'first', unanswered: 2),
    );
    expect(first.recipients.map((item) => item.id),
        ['unanswered-0', 'unanswered-1']);
    expect(first.selectedCount, 2);
    first.toggle('unanswered-0');
    first.chooseTemplate(OfficerNotificationTemplate.friendly);
    first.edit('虛構自訂提醒');
    first.preview();
    first.recordLocally();
    expect(first.recorded, isTrue);

    expect(
      controller.notificationDraftFor(
        lineupReport(gameId: 'first', unanswered: 2),
      ),
      same(first),
    );
    final second = controller.notificationDraftFor(
      lineupReport(gameId: 'second', unanswered: 1),
    );
    expect(second, isNot(same(first)));
    expect(second.selectedCount, 1);
    expect(second.recorded, isFalse);
  });

  testWidgets(
      'notification draft selection preview and local record never send',
      (tester) async {
    final draft = OfficerNotificationDraft(
      lineupReport(unanswered: 2),
    );
    await tester.pumpWidget(MaterialApp(
      home: OfficerNotificationDraftPage(draft: draft, offline: true),
    ));
    expect(find.byKey(const ValueKey('notification-draft-local-only')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('notification-draft-offline')),
        findsOneWidget);
    expect(find.text('收件人 2/2'), findsOneWidget);
    await tester.tap(
      find.byKey(const ValueKey('notification-recipient-unanswered-0')),
    );
    await tester.pump();
    expect(find.text('收件人 1/2'), findsOneWidget);
    await tester.enterText(
      find.byKey(const ValueKey('notification-draft-message')),
      '只存在本機的虛構提醒',
    );
    await tester.drag(find.byType(ListView).first, const Offset(0, -700));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('notification-draft-preview')));
    await tester.pump();
    expect(find.byKey(const ValueKey('notification-draft-confirmation')),
        findsOneWidget);
    await tester.drag(find.byType(ListView).first, const Offset(0, -400));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('notification-draft-record')));
    await tester.pump();
    expect(find.byKey(const ValueKey('notification-draft-recorded')),
        findsOneWidget);
    expect(find.text('沒有通知被傳送，也沒有資料被儲存。'), findsOneWidget);
  });

  testWidgets('notification draft uses server count and exact confirmation',
      (tester) async {
    final publisher = PreviewingPublisher();
    // Production reports use opaque person IDs; make this test use the API form.
    final serverDraft = OfficerNotificationDraft(SingleGameReportUiModel(
      gameId: 'game_44',
      gameLabel: '測試賽事',
      generatedAt: DateTime.utc(2026),
      historyGames: 1,
      historyLimit: 12,
      minimumResponseRate: 60,
      attending: const [],
      notAttending: const [],
      notYetReplied: const [
        NotYetRepliedUiModel(
            id: 'person_2',
            displayName: '甲',
            observedReplies: 0,
            observedGames: 1,
            responseRate: 0,
            participationRate: 0,
            nonparticipationRate: 0),
        NotYetRepliedUiModel(
            id: 'person_3',
            displayName: '乙',
            observedReplies: 0,
            observedGames: 1,
            responseRate: 0,
            participationRate: 0,
            nonparticipationRate: 0),
      ],
    ));
    await tester.pumpWidget(MaterialApp(
        home: OfficerNotificationDraftPage(
      draft: serverDraft,
      offline: false,
      publishingClient: publisher,
    )));
    final serverPreview =
        find.byKey(const ValueKey('notification-draft-server-preview'));
    await tester.drag(find.byType(ListView).first, const Offset(0, -900));
    await tester.pumpAndSettle();
    await tester.tap(serverPreview);
    await tester.pumpAndSettle();
    expect(publisher.previews.single['audience']['person_ids'],
        ['person_2', 'person_3']);
    expect(find.text('伺服器確認收件人：2 人'), findsOneWidget);
    expect(publisher.confirms, isEmpty);
    await tester.tap(
      find.byKey(const ValueKey('notification-recipient-person_2')),
    );
    await tester.pumpAndSettle();
    expect(find.text('伺服器確認收件人：2 人'), findsNothing);
  });

  testWidgets(
      'offline injected publisher remains local-only and is never called',
      (tester) async {
    final publisher = PreviewingPublisher();
    await tester.pumpWidget(MaterialApp(
      home: OfficerNotificationDraftPage(
        draft: OfficerNotificationDraft(lineupReport(unanswered: 1)),
        offline: true,
        publishingClient: publisher,
      ),
    ));
    expect(find.text('本機草稿，不會送出'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('notification-draft-server-preview')),
      findsNothing,
    );
    expect(publisher.previews, isEmpty);
    expect(publisher.confirms, isEmpty);
  });

  testWidgets('publish scope loss clears preview and rejects stale completion',
      (tester) async {
    final transport = ReportTransport();
    final session =
        SessionController(transport, MemoryStore(), 'scope', SecureIds());
    await session.accept(const SessionEnvelope(
      accessToken: 'access',
      refreshToken: 'refresh-token-with-at-least-32-characters',
      sessionId: 'session',
      expiresIn: 900,
    ));
    const officer = Person('person_1', 'Officer',
        ['games:read', 'attendance:report:read', 'notifications:publish'],
        accessLevel: AccessLevel.officer);
    final scope = OfficerNotificationPublishScope(session, officer, true);
    final publisher = DelayedPreviewPublisher();
    final draft = OfficerNotificationDraft(SingleGameReportUiModel(
      gameId: 'game_44',
      gameLabel: '測試',
      generatedAt: DateTime.utc(2026),
      historyGames: 1,
      historyLimit: 12,
      minimumResponseRate: 60,
      attending: const [],
      notAttending: const [],
      notYetReplied: const [
        NotYetRepliedUiModel(
            id: 'person_2',
            displayName: '甲',
            observedReplies: 0,
            observedGames: 1,
            responseRate: 0,
            participationRate: 0,
            nonparticipationRate: 0)
      ],
    ));
    await tester.pumpWidget(MaterialApp(
        home: OfficerNotificationDraftPage(
      draft: draft,
      offline: false,
      publishingClient: publisher,
      publishScope: scope,
    )));
    await tester.drag(find.byType(ListView).first, const Offset(0, -900));
    await tester
        .tap(find.byKey(const ValueKey('notification-draft-server-preview')));
    await tester.pump();
    scope.update(
        const Person('person_1', 'Officer', ['games:read'],
            accessLevel: AccessLevel.officer),
        true);
    publisher.response.complete({
      'recipient_count': 1,
      'revision': 'a' * 64,
      'confirmation_text': 'PUBLISH 1'
    });
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('notification-draft-server-preview')),
        findsNothing);
    expect(find.byKey(const ValueKey('notification-draft-server-confirm')),
        findsNothing);
    expect(publisher.confirms, isEmpty);
    scope.dispose();
  });
  test('attendance insights use only loaded report counts and honest labels',
      () {
    final report = DeterministicFakeOfficerReportRepository.fictionalReport;
    final insights = AttendanceInsights(report);

    expect(insights.attending, 1);
    expect(insights.unavailable, 0);
    expect(insights.unanswered, 1);
    expect(insights.responsePercent, 50);
    expect(insights.availabilityPercent, 100);
    expect(insights.isSmallSample, isTrue);
    expect(insights.callout(offline: true), contains('可能過期'));
    expect(insights.callout(offline: false), contains('樣本很少'));
  });

  test('lineup draft starts fine empty and enforces Web assignment invariants',
      () {
    final report = SingleGameReportUiModel(
      gameId: 'lineup',
      gameLabel: 'Lineup',
      generatedAt: DateTime.utc(2026),
      historyGames: 1,
      historyLimit: 12,
      minimumResponseRate: 60,
      attending: List.generate(
        10,
        (index) => ReportParticipantUiModel(
          id: 'attending-$index',
          displayName: '出席 $index',
        ),
      ),
      notAttending: const [
        ReportParticipantUiModel(id: 'unavailable', displayName: '不出席'),
      ],
      notYetReplied: const [
        NotYetRepliedUiModel(
          id: 'unanswered',
          displayName: '未回覆',
          observedReplies: 0,
          observedGames: 1,
          responseRate: 0,
          participationRate: 0,
          nonparticipationRate: 0,
        ),
      ],
    );
    final draft = LineupDraft.fromReport(report);
    expect(draft.battingOrder, isEmpty);
    expect(draft.reserves, hasLength(10));
    expect(draft.missingStarterCount, 9);
    expect(draft.unansweredCount, 1);
    expect(draft.isReady, isFalse);
    expect(
        draft.pool.map((player) => player.id), isNot(contains('unavailable')));

    final ready = LineupDraft.fromReport(
      lineupReport(attending: 10, unanswered: 0),
    );
    expect(ready.isReady, isFalse);
    expect(ready.missingStarterCount, 9);
    expect(ready.reserves, hasLength(10));
    ready.assignFieldPosition(LineupFieldPosition.pitcher, ready.pool[0]);
    ready.assignFieldPosition(LineupFieldPosition.catcher, ready.pool[0]);
    expect(ready.fieldAssignments[LineupFieldPosition.pitcher], isNull);
    expect(
        ready.fieldAssignments[LineupFieldPosition.catcher]!.id, 'quality-0');
    expect(ready.hasUniqueFieldAssignments, isTrue);
    ready.assignBattingSlot(1, ready.pool[0]);
    ready.assignBattingSlot(2, ready.pool[0]);
    expect(ready.battingOrder[1], isNull);
    expect(ready.battingOrder[2]!.id, 'quality-0');
    expect(ready.hasUniqueBattingOrder, isTrue);
    ready.assignFieldPosition(LineupFieldPosition.catcher, null);
    expect(ready.battingOrder, isEmpty);
    ready.assignFieldPosition(LineupFieldPosition.pitcher, ready.pool[1]);
    ready.assignBattingSlot(1, ready.pool[1]);
    ready.assignFieldPosition(
        LineupFieldPosition.designatedHitter, ready.pool[2]);
    expect(ready.nonBattingPitcher!.id, 'quality-1');
    expect(ready.battingOrder, isEmpty);
    expect(ready.hasUniqueFieldAssignments, isTrue);
    expect(ready.hasUniqueBattingOrder, isTrue);

    final complete = LineupDraft.fromReport(
      lineupReport(attending: 10, unanswered: 0),
    );
    for (var index = 0; index < 9; index++) {
      complete.assignFieldPosition(
          LineupFieldPosition.values[index], complete.pool[index]);
      complete.assignBattingSlot(index + 1, complete.pool[index]);
    }
    expect(complete.battingOrder, hasLength(9));
    expect(complete.isReady, isTrue);
    expect(complete.hasUniqueFieldAssignments, isTrue);
    expect(complete.hasUniqueBattingOrder, isTrue);
  });

  testWidgets(
      'Lineup Lab starts fine empty with nine independently selectable slots',
      (tester) async {
    await pumpLineupLab(
      tester,
      lineupReport(attending: 8, unanswered: 2),
    );

    expect(find.byKey(const ValueKey('lineup-warning')), findsOneWidget);
    expect(find.text('先發 0/9・缺 9 人・候補／未安排 8 人・尚未回覆 2 人'), findsOneWidget);
    for (var slot = 1; slot <= 9; slot++) {
      expect(find.byKey(ValueKey('lineup-slot-$slot')), findsOneWidget);
    }
    expect(find.byKey(const ValueKey('lineup-empty-slot-9')), findsOneWidget);
    expect(
        find.byKey(const ValueKey('lineup-batting-select-1')), findsOneWidget);
  });

  test('coarse fine and all resets have isolated Web parity boundaries', () {
    final draft = LineupDraft.fromReport(
      lineupReport(attending: 3, unanswered: 0),
    );
    draft.assignCoarseRole(draft.pool[0], CoarseLineupRole.pitcher);
    draft.assignFieldPosition(LineupFieldPosition.catcher, draft.pool[0]);
    draft.assignBattingSlot(1, draft.pool[0]);

    draft.resetCoarse();
    expect(draft.coarseRoles, isEmpty);
    expect(draft.fieldAssignments, isNotEmpty);
    expect(draft.battingOrder[1]!.id, 'quality-0');

    draft.assignCoarseRole(draft.pool[1], CoarseLineupRole.infield);
    draft.resetFine();
    expect(draft.coarseRoles['quality-1'], CoarseLineupRole.infield);
    expect(draft.fieldAssignments, isEmpty);
    expect(draft.battingOrder, isEmpty);

    draft.assignFieldPosition(LineupFieldPosition.firstBase, draft.pool[1]);
    draft.assignBattingSlot(3, draft.pool[1]);
    draft.clearAll();
    expect(draft.coarseRoles, isEmpty);
    expect(draft.fieldAssignments, isEmpty);
    expect(draft.battingOrder, isEmpty);

    final late = ReportParticipantUiModel(
      id: 'late',
      displayName: 'Late',
      reply: AttendanceReply.arrivingLate,
    );
    final lateDraft = LineupDraft.fromReport(SingleGameReportUiModel(
      gameId: 'late',
      gameLabel: 'late',
      generatedAt: DateTime.utc(2026),
      historyGames: 1,
      historyLimit: 12,
      minimumResponseRate: 60,
      attending: [late],
      notAttending: const [],
      notYetReplied: const [],
    ));
    lateDraft.assignCoarseRole(late, CoarseLineupRole.outfield);
    lateDraft.assignFieldPosition(LineupFieldPosition.leftField, late);
    expect(lateDraft.coarseRoles['late'], CoarseLineupRole.outfield);
    expect(lateDraft.fieldAssignments, isEmpty);
  });

  testWidgets('coarse reset confirmation cancel preserves and confirm clears',
      (tester) async {
    await pumpLineupLab(
      tester,
      lineupReport(attending: 3, unanswered: 0),
      fine: false,
    );
    final role = find.byKey(
      const ValueKey('lineup-coarse-quality-0-pitcher'),
    );
    await tester.tap(role);
    await tester.pumpAndSettle();
    expect(tester.widget<ChoiceChip>(role).selected, isTrue);

    await tester.tap(find.byKey(const ValueKey('lineup-reset-coarse')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-reset-cancel')));
    await tester.pumpAndSettle();
    expect(tester.widget<ChoiceChip>(role).selected, isTrue);

    await tester.tap(find.byKey(const ValueKey('lineup-reset-coarse')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-reset-confirm')));
    await tester.pumpAndSettle();
    expect(tester.widget<ChoiceChip>(role).selected, isFalse);
  });

  testWidgets('fine reset and clear-all confirmations keep exact scopes',
      (tester) async {
    final report = lineupReport(attending: 3, unanswered: 0);
    final controller = await pumpLineupLab(tester, report, fine: false);
    final draft = controller.lineupDraftFor(report);
    draft.assignCoarseRole(draft.pool[0], CoarseLineupRole.catcher);
    draft.coarseCoaches.add(draft.pool[0].id);
    draft.fineCoaches.add(draft.pool[1].id);
    draft.assignFieldPosition(LineupFieldPosition.firstBase, draft.pool[0]);
    draft.assignBattingSlot(1, draft.pool[0]);

    await tester.tap(find.byKey(const ValueKey('lineup-reset-fine')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-reset-cancel')));
    await tester.pumpAndSettle();
    expect(draft.fieldAssignments, isNotEmpty);
    expect(draft.battingOrder, isNotEmpty);

    await tester.tap(find.byKey(const ValueKey('lineup-reset-fine')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-reset-confirm')));
    await tester.pumpAndSettle();
    expect(draft.fieldAssignments, isEmpty);
    expect(draft.battingOrder, isEmpty);
    expect(draft.coarseRoles, isNotEmpty);
    expect(draft.coarseCoaches, isNotEmpty);
    expect(draft.fineCoaches, isEmpty);

    draft.assignFieldPosition(LineupFieldPosition.firstBase, draft.pool[0]);
    draft.assignBattingSlot(1, draft.pool[0]);
    await tester.tap(find.byKey(const ValueKey('lineup-clear-all')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-reset-cancel')));
    await tester.pumpAndSettle();
    expect(draft.coarseRoles, isNotEmpty);
    expect(draft.fieldAssignments, isNotEmpty);

    await tester.tap(find.byKey(const ValueKey('lineup-clear-all')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-reset-confirm')));
    await tester.pumpAndSettle();
    expect(draft.coarseRoles, isEmpty);
    expect(draft.coarseCoaches, isEmpty);
    expect(draft.fineCoaches, isEmpty);
    expect(draft.fieldAssignments, isEmpty);
    expect(draft.battingOrder, isEmpty);
  });

  testWidgets(
      'Lineup Lab coarse fine field DH annotations and copy use local ports',
      (tester) async {
    final copyPort = RecordingLineupCopyPort();
    final report = lineupReport(attending: 3, unanswered: 0);
    final controller = await pumpLineupLab(
      tester,
      report,
      fine: false,
      copyPort: copyPort,
    );

    expect(find.byKey(const ValueKey('lineup-coarse-coaches')), findsOneWidget);
    expect(find.text('Quality 2 #3（早走）'), findsWidgets);
    await tester.tap(
      find.byKey(const ValueKey('lineup-coarse-coach-quality-0')),
    );
    await tester.tap(
      find.byKey(const ValueKey('lineup-coarse-quality-0-pitcher')),
    );
    await tester.pumpAndSettle();
    expect(copyPort.summaries, isEmpty);
    await tester.ensureVisible(
      find.byKey(const ValueKey('lineup-copy-summary')),
    );
    await tester.tap(find.byKey(const ValueKey('lineup-copy-summary')));
    await tester.pumpAndSettle();
    expect(copyPort.summaries.single, contains('教練：Quality 0 #1'));
    expect(copyPort.summaries.single, contains('投手：Quality 0 #1'));

    await tester.ensureVisible(find.text('細排'));
    await tester.tap(find.text('細排'));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('lineup-fine-coach-quality-1')),
    );
    expect(
        controller.lineupDraftFor(report).fineCoaches, contains('quality-1'));
    await tester.tap(find.byKey(const ValueKey('lineup-batting-select-1')));
    await tester.pumpAndSettle();
    expect(find.text('目前沒有已安排守位且符合細排資格的球員。'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('lineup-batting-clear-1')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byKey(const ValueKey('lineup-position-P')),
    );
    await tester.tap(find.byKey(const ValueKey('lineup-position-P')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('lineup-position-P-player-quality-0')),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView).last, const Offset(0, 1600));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byKey(const ValueKey('lineup-batting-select-1')),
    );
    await tester.tap(find.byKey(const ValueKey('lineup-batting-select-1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lineup-batting-1-player-quality-0')),
        findsOneWidget);
    await tester.tap(
      find.byKey(const ValueKey('lineup-batting-1-player-quality-0')),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView).last, const Offset(0, -1600));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-position-DH')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('lineup-position-DH-player-quality-1')),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lineup-non-batting-pitcher')),
        findsOneWidget);
    final draft = controller.lineupDraftFor(report);
    expect(draft.battingOrder, isEmpty);
    expect(draft.nonBattingPitcher!.id, 'quality-0');

    await tester.drag(find.byType(ListView).last, const Offset(0, 1600));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byKey(const ValueKey('lineup-batting-select-1')),
    );
    await tester.tap(find.byKey(const ValueKey('lineup-batting-select-1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lineup-batting-1-player-quality-0')),
        findsNothing);
    await tester.tap(
      find.byKey(const ValueKey('lineup-batting-1-player-quality-1')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-batting-select-2')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('lineup-batting-2-player-quality-1')),
    );
    await tester.pumpAndSettle();
    expect(draft.battingOrder[1], isNull);
    expect(draft.battingOrder[2]!.id, 'quality-1');

    await tester.drag(find.byType(ListView).last, const Offset(0, -1600));
    await tester.pumpAndSettle();
    await tester
        .ensureVisible(find.byKey(const ValueKey('lineup-position-DH')));
    await tester.tap(find.byKey(const ValueKey('lineup-position-DH')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-position-clear')));
    await tester.pumpAndSettle();
    expect(draft.battingOrder, isEmpty);
  });

  testWidgets(
      'Lineup Lab retains draft after system back and resets for another report',
      (tester) async {
    SingleGameReportUiModel report(String id, String prefix) =>
        SingleGameReportUiModel(
          gameId: id,
          gameLabel: id,
          generatedAt: DateTime.utc(2026),
          historyGames: 1,
          historyLimit: 12,
          minimumResponseRate: 60,
          attending: List.generate(
            10,
            (index) => ReportParticipantUiModel(
              id: '$prefix-$index',
              displayName: '$prefix $index',
            ),
          ),
          notAttending: const [],
          notYetReplied: const [],
        );
    final controller = controllerFor();
    await controller.applyFreshPrincipal(
      principalId: 'officer',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    controller
      ..report = report('first', 'first')
      ..state = OfficerReportViewState.ready;
    await tester.pumpWidget(
        MaterialApp(home: OfficerReportPanel(controller: controller)));
    await tester.tap(find.byKey(const ValueKey('lineup-lab-entry')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('lineup-coarse-first-0-pitcher')),
    );
    await tester.pumpAndSettle();
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lineup-lab-entry')));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<ChoiceChip>(
              find.byKey(const ValueKey('lineup-coarse-first-0-pitcher')))
          .selected,
      isTrue,
    );

    await tester.pageBack();
    controller
      ..report = report('second', 'second')
      ..state = OfficerReportViewState.ready;
    await tester.pumpWidget(
        MaterialApp(home: OfficerReportPanel(controller: controller)));
    await tester.tap(find.byKey(const ValueKey('lineup-lab-entry')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lineup-coarse-second-0-pitcher')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('lineup-coarse-first-0-pitcher')),
        findsNothing);
    await tester.pageBack();
    await tester.pumpWidget(
      MaterialApp(home: OfficerReportPanel(controller: controller)),
    );
    await tester.tap(find.byKey(const ValueKey('lineup-lab-entry')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lineup-coarse-second-0-pitcher')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('lineup-coarse-first-0-pitcher')),
        findsNothing);
  });

  test('canonical adapter uses exact read path and default bounded query',
      () async {
    final transport = ReportTransport();
    final repository = CanonicalOfficerReportRepository(
      await reportApi(transport),
    );
    final report = await repository.readSingleGame(
      principalId: 'officer',
      gameId: 'game_44',
    );
    expect(transport.calls, [
      (
        'GET',
        '/games/game_44/attendance-report?history_limit=12&minimum_response_rate=60'
      )
    ]);
    expect(report.attending.single.displayName, '已出席');
    expect(report.attending.single.memberNumber, 18);
    expect(report.notAttending.single.memberNumber, isNull);
    expect(report.notAttending.single.reply, AttendanceReply.notAttending);
    expect(report.notAttending.single.displayName, '不出席');
    expect(report.notYetReplied.single.displayName, '尚未回覆');
    expect(report.notYetReplied.single.responseRate, 88);
    expect(report.historyGames, 8);
    expect(report.historyLimit, 12);
    expect(report.minimumResponseRate, 60);
    expect(report.generatedAt, DateTime.utc(2026, 8, 18, 12));
  });

  test('not-attending member number maps and survives durable cache', () async {
    for (final entry in <(String, Object?)>[
      ('number', 27),
      ('null', null),
      ('omitted', 'omitted'),
    ]) {
      final transport = ReportTransport();
      final person = <String, dynamic>{
        'person_id': 'person_3',
        'display_name': 'Not attending',
        'reply': 'not_attending',
      };
      if (entry.$2 != 'omitted') person['member_number'] = entry.$2;
      transport.response.body!['not_attending'] = [person];
      final report = await CanonicalOfficerReportRepository(
        await reportApi(transport),
      ).readSingleGame(principalId: 'officer', gameId: 'game_44');
      final mapped = report.notAttending.single;
      expect(mapped.reply, AttendanceReply.notAttending, reason: entry.$1);
      expect(mapped.memberNumber, entry.$2 == 27 ? 27 : isNull,
          reason: entry.$1);

      final cache = DurablePrincipalOfficerReportCache(
        MemoryStore(),
        'install-${entry.$1}',
      );
      await cache.write('officer', report);
      final restored = await cache.read('officer', 'game_44');
      expect(restored!.notAttending.single.reply, AttendanceReply.notAttending,
          reason: entry.$1);
      expect(restored.notAttending.single.memberNumber,
          entry.$2 == 27 ? 27 : isNull,
          reason: entry.$1);
    }
  });

  test('attendance report rejects malformed member numbers', () {
    for (final value in ['18', -1, 1000]) {
      expect(
        () => AttendanceReportPerson.fromJson({
          'person_id': 'person_1',
          'display_name': '球員',
          'reply': 'attending',
          'member_number': value,
        }),
        throwsA(isA<ContractException>()),
      );
    }
  });

  test('server-owned role and exact capability must both grant reports', () {
    for (final accessLevel in AccessLevel.values) {
      for (final hasCapability in [false, true]) {
        final person = Person(
          'p',
          'Reader',
          hasCapability
              ? const ['attendance:report:read']
              : const ['games:read'],
          accessLevel: accessLevel,
        );
        expect(
          person.canReadAttendanceReport,
          accessLevel != AccessLevel.basic && hasCapability,
          reason: '$accessLevel capability=$hasCapability',
        );
      }
    }
  });

  test('fresh lifecycle purges admin to officer but retains officer to admin',
      () async {
    final store = MemoryStore();
    final cache = DurablePrincipalOfficerReportCache(store, 'install');
    const grant = ['attendance:report:read'];
    const admin = Person('p', 'Admin', grant, accessLevel: AccessLevel.admin);
    const officer =
        Person('p', 'Officer', grant, accessLevel: AccessLevel.officer);

    await cache.write(
        'p', DeterministicFakeOfficerReportRepository.fictionalReport);
    await reconcileFreshReportPrincipal(
        cache: cache, previous: admin, current: officer);
    expect(await cache.read('p', 'fictional-game'), isNull);

    await cache.write(
        'p', DeterministicFakeOfficerReportRepository.fictionalReport);
    await reconcileFreshReportPrincipal(
        cache: cache, previous: officer, current: admin);
    expect(await cache.read('p', 'fictional-game'), isNotNull);
    expect(
      const Person('p', 'Basic', grant).canReadAttendanceReport,
      isFalse,
    );
  });
  test('read grant alone controls discovery and route fail-closed', () async {
    final controller = controllerFor();
    await controller.applyFreshPrincipal(
      principalId: 'basic-principal',
      reportReadGrant: const ManagementReportReadGrant.denied(),
    );
    expect(controller.policy.bottomDestinations, hasLength(4));
    expect(controller.open(ManagementPresentationRoute.reportsHub), isFalse);
    expect(
      controller.open(ManagementPresentationRoute.singleGameReport),
      isFalse,
    );
    expect(controller.route, ManagementPresentationRoute.home);

    await controller.applyFreshPrincipal(
      principalId: 'read-principal',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    expect(controller.policy.bottomDestinations.length, lessThanOrEqualTo(5));
    expect(controller.open(ManagementPresentationRoute.reportsHub), isTrue);
    expect(
      controller.open(ManagementPresentationRoute.singleGameReport),
      isTrue,
    );
    expect(controller.mutationsEnabled, isFalse);
  });

  test(
    'deterministic fake exposes both cohorts and insight without network',
    () async {
      final repository = DeterministicFakeOfficerReportRepository();
      final first = await repository.readSingleGame(
        principalId: 'p',
        gameId: 'fictional-game',
      );
      final second = await repository.readSingleGame(
        principalId: 'p',
        gameId: 'fictional-game',
      );
      expect(first.attending.single.displayName, '已回覆隊員');
      expect(first.notYetReplied.single.displayName, '尚未回覆隊員');
      expect(first.notYetReplied.single.observedGames, 8);
      expect(second.gameId, first.gameId);
      expect(repository.reads, [
        ('p', 'fictional-game'),
        ('p', 'fictional-game'),
      ]);
    },
  );

  test(
    'fresh downgrade revokes route and clears current principal cache',
    () async {
      final cache = InMemoryPrincipalOfficerReportCache();
      final controller = controllerFor(cache: cache);
      await controller.applyFreshPrincipal(
        principalId: 'p',
        reportReadGrant: const ManagementReportReadGrant.granted(),
      );
      await controller.loadSingleGame(
        'fictional-game',
        online: true,
        syncedAt: DateTime.utc(2026, 8, 19),
      );
      expect(controller.route, ManagementPresentationRoute.singleGameReport);
      await controller.applyFreshPrincipal(
        principalId: 'p',
        reportReadGrant: const ManagementReportReadGrant.denied(),
      );
      expect(controller.route, ManagementPresentationRoute.home);
      expect(controller.report, isNull);
      expect(cache.clearedPrincipals, ['p']);
      expect(await cache.read('p', 'fictional-game'), isNull);
    },
  );

  test(
    'fresh identity change revokes route and clears old principal cache',
    () async {
      final cache = InMemoryPrincipalOfficerReportCache();
      final controller = controllerFor(cache: cache);
      await controller.applyFreshPrincipal(
        principalId: 'old',
        reportReadGrant: const ManagementReportReadGrant.granted(),
      );
      await controller.loadSingleGame('fictional-game', online: true);
      await controller.applyFreshPrincipal(
        principalId: 'new',
        reportReadGrant: const ManagementReportReadGrant.granted(),
      );
      expect(controller.route, ManagementPresentationRoute.home);
      expect(cache.clearedPrincipals, ['old']);
      expect(await cache.read('old', 'fictional-game'), isNull);
    },
  );

  test('offline cache is principal-scoped and always read-only', () async {
    final cache = InMemoryPrincipalOfficerReportCache();
    await cache.write(
      'p',
      DeterministicFakeOfficerReportRepository.fictionalReport,
    );
    final controller = controllerFor(cache: cache);
    await controller.applyFreshPrincipal(
      principalId: 'p',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await controller.loadSingleGame('fictional-game', online: false);
    expect(controller.state, OfficerReportViewState.offlineCached);
    expect(controller.mutationsEnabled, isFalse);
    expect(controller.report, isNotNull);
  });

  test(
    'controller maps retryable forbidden session and empty states',
    () async {
      for (final entry in <Object, OfficerReportViewState>{
        const RetryableOfficerReportException():
            OfficerReportViewState.retryableError,
        const ForbiddenOfficerReportException():
            OfficerReportViewState.forbidden,
        const ExpiredOfficerReportSessionException():
            OfficerReportViewState.sessionExpired,
        const ContractOfficerReportException():
            OfficerReportViewState.contractError,
      }.entries) {
        final controller = controllerFor(
          repository: DeterministicFakeOfficerReportRepository(
            failure: entry.key,
          ),
        );
        await controller.applyFreshPrincipal(
          principalId: 'p',
          reportReadGrant: const ManagementReportReadGrant.granted(),
        );
        await controller.loadSingleGame('fictional-game', online: true);
        expect(controller.state, entry.value);
      }

      final emptyController = controllerFor(
        repository: DeterministicFakeOfficerReportRepository(
          report: SingleGameReportUiModel(
            gameId: 'empty',
            gameLabel: '空白賽事',
            generatedAt: DateTime.utc(2026),
            historyGames: 0,
            historyLimit: 12,
            minimumResponseRate: 60,
            attending: const [],
            notAttending: const [],
            notYetReplied: const [],
          ),
        ),
      );
      await emptyController.applyFreshPrincipal(
        principalId: 'p',
        reportReadGrant: const ManagementReportReadGrant.granted(),
      );
      await emptyController.loadSingleGame('empty', online: true);
      expect(emptyController.state, OfficerReportViewState.empty);
    },
  );

  test('fresh server denial revokes report and purges principal cache',
      () async {
    final cache = InMemoryPrincipalOfficerReportCache();
    await cache.write(
      'p',
      DeterministicFakeOfficerReportRepository.fictionalReport,
    );
    final controller = controllerFor(
      cache: cache,
      repository: DeterministicFakeOfficerReportRepository(
        failure: const ForbiddenOfficerReportException(),
      ),
    );
    await controller.applyFreshPrincipal(
      principalId: 'p',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await controller.loadSingleGame('fictional-game', online: true);
    expect(controller.route, ManagementPresentationRoute.home);
    expect(controller.state, OfficerReportViewState.forbidden);
    expect(await cache.read('p', 'fictional-game'), isNull);
  });

  testWidgets('denied principal cannot discover management', (tester) async {
    final controller = controllerFor();
    await controller.applyFreshPrincipal(
      principalId: 'basic',
      reportReadGrant: const ManagementReportReadGrant.denied(),
    );
    await tester.pumpWidget(
      MaterialApp(home: OfficerReadOnlyShell(controller: controller)),
    );
    expect(find.text('管理'), findsNothing);
    expect(
      find.byKey(const ValueKey('single-game-report-entry')),
      findsNothing,
    );
  });

  testWidgets('direct canonical management route fails closed for Basic',
      (tester) async {
    for (final person in [
      const Person('basic', 'Basic', ['attendance:report:read']),
      const Person('officer', 'Officer', ['games:read'],
          accessLevel: AccessLevel.officer),
      const Person('admin', 'Admin', ['games:read'],
          accessLevel: AccessLevel.admin),
    ]) {
      final transport = ReportTransport();
      final api = await reportApi(transport);
      await tester.pumpWidget(MaterialApp(
        home: CanonicalManagementReportsPage(
          api: api,
          person: person,
          games: [Game('game_44', DateTime.utc(2026), 60, null, 'A', 'B')],
          online: true,
        ),
      ));
      expect(find.byKey(const ValueKey('management-route-forbidden')),
          findsOneWidget);
      expect(find.text('唯讀出席報表'), findsNothing);
      expect(transport.calls, isEmpty);
    }
  });

  testWidgets('canonical 404 and 422 settle into fail-closed UI states',
      (tester) async {
    for (final entry in [
      (404, 'resource_not_found'),
      (422, 'validation_failed')
    ]) {
      final transport = ReportTransport()
        ..response = ApiResponse(entry.$1, reportError(entry.$2));
      final controller = OfficerReportController(
        repository:
            CanonicalOfficerReportRepository(await reportApi(transport)),
        cache: InMemoryPrincipalOfficerReportCache(),
      );
      await controller.applyFreshPrincipal(
        principalId: 'officer',
        reportReadGrant: const ManagementReportReadGrant.granted(),
      );
      await controller.loadSingleGame('game_44', online: true);
      expect(
        controller.state,
        entry.$1 == 404
            ? OfficerReportViewState.forbidden
            : OfficerReportViewState.contractError,
      );
      await tester.pumpWidget(
        MaterialApp(home: OfficerReportPanel(controller: controller)),
      );
      expect(find.byKey(ValueKey('officer-report-${controller.state.name}')),
          findsOneWidget);
      expect(find.text('送出回覆'), findsNothing);
    }
  });

  test('durable cache survives reconstruction and isolates principals',
      () async {
    final store = MemoryStore();
    final first = DurablePrincipalOfficerReportCache(store, 'install-a');
    await first.write(
        'officer', DeterministicFakeOfficerReportRepository.fictionalReport);
    final restarted = DurablePrincipalOfficerReportCache(store, 'install-a');
    final restored = await restarted.read('officer', 'fictional-game');
    expect(restored, isNotNull);
    expect(restored!.attending.single.memberNumber, 18);
    final key = store.values.keys.single;
    final legacy = jsonDecode(store.values[key]!) as Map<String, dynamic>;
    final legacyReport =
        (legacy['reports'] as List<dynamic>).single as Map<String, dynamic>;
    for (final person in legacyReport['attending'] as List<dynamic>) {
      (person as Map<String, dynamic>).remove('member_number');
    }
    await store.write(key, jsonEncode(legacy));
    expect(
      (await restarted.read('officer', 'fictional-game'))!
          .attending
          .single
          .memberNumber,
      isNull,
    );
    expect(await restarted.read('basic', 'fictional-game'), isNull);
    expect(
      await DurablePrincipalOfficerReportCache(store, 'install-b')
          .read('officer', 'fictional-game'),
      isNull,
    );
  });

  test('durable cache corrupt/version mismatch clears and fails closed',
      () async {
    for (final raw in ['not-json', '{"version":2,"reports":[]}']) {
      final store = MemoryStore();
      final cache = DurablePrincipalOfficerReportCache(store, 'install');
      await store.write('officer-report-cache:v1:install:officer', raw);
      expect(await cache.read('officer', 'game'), isNull);
      expect(store.values, isEmpty);
    }
  });

  test('durable cache rejects out-of-contract member number', () async {
    final store = MemoryStore();
    final cache = DurablePrincipalOfficerReportCache(store, 'install');
    await cache.write(
      'officer',
      DeterministicFakeOfficerReportRepository.fictionalReport,
    );
    final key = store.values.keys.single;
    final payload = jsonDecode(store.values[key]!) as Map<String, dynamic>;
    final reports = payload['reports'] as List<dynamic>;
    final report = reports.single as Map<String, dynamic>;
    final attending = report['attending'] as List<dynamic>;
    (attending.single as Map<String, dynamic>)['member_number'] = 1000;
    await store.write(key, jsonEncode(payload));

    expect(await cache.read('officer', 'fictional-game'), isNull);
    expect(store.values, isEmpty);
  });

  test('single blob failed write preserves prior durable report', () async {
    final store = FailingWriteStore();
    final cache = DurablePrincipalOfficerReportCache(store, 'install');
    await cache.write(
        'officer', DeterministicFakeOfficerReportRepository.fictionalReport);
    final before = Map<String, String>.from(store.values);
    store.failNextWrite = true;
    expect(
      () => cache.write(
          'officer', DeterministicFakeOfficerReportRepository.fictionalReport),
      throwsA(isA<NetworkException>()),
    );
    expect(store.values, before);
  });

  test('durable cache is bounded and serializes low-sensitive fields only',
      () async {
    final store = MemoryStore();
    final cache = DurablePrincipalOfficerReportCache(store, 'install');
    for (var index = 0; index < 21; index++) {
      await cache.write('officer', reportWithId('game-$index'));
    }
    expect(await cache.read('officer', 'game-0'), isNull);
    expect(await cache.read('officer', 'game-20'), isNotNull);
    final raw = store.values.values.single;
    expect(
        utf8.encode(raw).length,
        lessThanOrEqualTo(
            DurablePrincipalOfficerReportCache.maximumEncodedBytes));
    for (final prohibited in [
      'token',
      'nonce',
      'provider',
      'contact',
      'admin_note',
      'audit',
      'raw_error',
    ]) {
      expect(raw, isNot(contains(prohibited)));
    }
  });

  test('oversized write preserves prior valid single blob', () async {
    final store = MemoryStore();
    final cache = DurablePrincipalOfficerReportCache(store, 'install');
    await cache.write(
        'officer', DeterministicFakeOfficerReportRepository.fictionalReport);
    final before = Map<String, String>.from(store.values);
    expect(
      () => cache.write('officer', largeBoundedReport()),
      throwsA(isA<FormatException>()),
    );
    expect(store.values, before);
  });

  test('oversized read deletes blob and fails closed', () async {
    final store = MemoryStore();
    final cache = DurablePrincipalOfficerReportCache(store, 'install');
    await store.write(
      'officer-report-cache:v1:install:officer',
      'x' * (DurablePrincipalOfficerReportCache.maximumEncodedBytes + 1),
    );
    expect(await cache.read('officer', 'game'), isNull);
    expect(store.values, isEmpty);
  });

  test('offline reconstructed cache requires a fresh granted controller',
      () async {
    final store = MemoryStore();
    final cache = DurablePrincipalOfficerReportCache(store, 'install');
    await cache.write(
        'officer', DeterministicFakeOfficerReportRepository.fictionalReport);
    final denied = OfficerReportController(
      repository: DeterministicFakeOfficerReportRepository(),
      cache: DurablePrincipalOfficerReportCache(store, 'install'),
    );
    await denied.applyFreshPrincipal(
      principalId: 'officer',
      reportReadGrant: const ManagementReportReadGrant.denied(),
    );
    await denied.loadSingleGame('fictional-game', online: false);
    expect(denied.state, OfficerReportViewState.forbidden);
    expect(denied.report, isNull);

    final granted = OfficerReportController(
      repository: DeterministicFakeOfficerReportRepository(),
      cache: DurablePrincipalOfficerReportCache(store, 'install'),
    );
    await granted.applyFreshPrincipal(
      principalId: 'officer',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await granted.loadSingleGame('fictional-game', online: false);
    expect(granted.state, OfficerReportViewState.offlineCached);
    expect(granted.mutationsEnabled, isFalse);
  });

  test('durable cache is purged on downgrade identity change and session end',
      () async {
    final store = MemoryStore();
    Future<void> seed(String principal) =>
        DurablePrincipalOfficerReportCache(store, 'install').write(principal,
            DeterministicFakeOfficerReportRepository.fictionalReport);

    await seed('same');
    final downgrade = OfficerReportController(
      repository: DeterministicFakeOfficerReportRepository(),
      cache: DurablePrincipalOfficerReportCache(store, 'install'),
    );
    await downgrade.applyFreshPrincipal(
      principalId: 'same',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await downgrade.applyFreshPrincipal(
      principalId: 'same',
      reportReadGrant: const ManagementReportReadGrant.denied(),
    );
    expect(
        await DurablePrincipalOfficerReportCache(store, 'install')
            .read('same', 'fictional-game'),
        isNull);

    await seed('old');
    final identity = OfficerReportController(
      repository: DeterministicFakeOfficerReportRepository(),
      cache: DurablePrincipalOfficerReportCache(store, 'install'),
    );
    await identity.applyFreshPrincipal(
      principalId: 'old',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await identity.applyFreshPrincipal(
      principalId: 'new',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    expect(
        await DurablePrincipalOfficerReportCache(store, 'install')
            .read('old', 'fictional-game'),
        isNull);

    await seed('expired');
    final expired = OfficerReportController(
      repository: DeterministicFakeOfficerReportRepository(
          failure: const ExpiredOfficerReportSessionException()),
      cache: DurablePrincipalOfficerReportCache(store, 'install'),
    );
    await expired.applyFreshPrincipal(
      principalId: 'expired',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await expired.loadSingleGame('fictional-game', online: true);
    expect(
        await DurablePrincipalOfficerReportCache(store, 'install')
            .read('expired', 'fictional-game'),
        isNull);

    await seed('logout');
    await DurablePrincipalOfficerReportCache(store, 'install')
        .clearPrincipal('logout');
    expect(
        await DurablePrincipalOfficerReportCache(store, 'install')
            .read('logout', 'fictional-game'),
        isNull);
  });

  test('installation aggregate presence and purge are physically scoped',
      () async {
    final store = MemoryStore();
    final current = DurablePrincipalOfficerReportCache(store, 'install');
    final other = DurablePrincipalOfficerReportCache(store, 'other');
    await current.write(
      'current-principal',
      DeterministicFakeOfficerReportRepository.fictionalReport,
    );
    await other.write(
      'other-principal',
      DeterministicFakeOfficerReportRepository.fictionalReport,
    );
    expect(await current.observeAnyPresence(), isTrue);
    await current.clearInstallation();
    expect(await current.observeAnyPresence(), isFalse);
    expect(await other.observeAnyPresence(), isTrue);
  });

  testWidgets('granted shell navigates and renders read-only report cohorts', (
    tester,
  ) async {
    final controller = controllerFor();
    await controller.applyFreshPrincipal(
      principalId: 'read',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await tester.pumpWidget(
      MaterialApp(home: OfficerReadOnlyShell(controller: controller)),
    );
    await tester.tap(find.text('管理'));
    await tester.pump();
    expect(find.text('單場出席報表'), findsOneWidget);
    await controller.loadSingleGame('fictional-game', online: true);
    await tester.pump();
    expect(find.text('出席'), findsOneWidget);
    expect(find.text('不出席'), findsOneWidget);
    expect(find.text('尚未回覆'), findsOneWidget);
    expect(find.text('觀察場次：8 / 12'), findsOneWidget);
    expect(find.text('最低回覆率：60%'), findsOneWidget);
    expect(find.textContaining('產生時間：2026-08-19'), findsOneWidget);
    await tester.scrollUntilVisible(find.textContaining('回覆率 88%'), 300);
    expect(find.textContaining('回覆率 88%'), findsOneWidget);
    expect(find.text('送出回覆'), findsNothing);
  });

  testWidgets('offline cached report has read-only semantics', (tester) async {
    final cache = InMemoryPrincipalOfficerReportCache();
    await cache.write(
      'read',
      DeterministicFakeOfficerReportRepository.fictionalReport,
    );
    final controller = controllerFor(cache: cache);
    await controller.applyFreshPrincipal(
      principalId: 'read',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await controller.loadSingleGame('fictional-game', online: false);
    await tester.pumpWidget(
      MaterialApp(home: OfficerReportPanel(controller: controller)),
    );
    final panel = find.byKey(
      const ValueKey('officer-report-offlineCached'),
    );
    expect(tester.getSemantics(panel).label, contains('離線快取唯讀報表'));
    expect(find.text('目前為離線快取，僅供讀取'), findsOneWidget);
    expect(controller.mutationsEnabled, isFalse);
  });

  testWidgets('debug report projection exposes only canonical bounded states',
      (tester) async {
    final ready = controllerFor();
    await ready.applyFreshPrincipal(
      principalId: 'ready-principal',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await ready.loadSingleGame('fictional-game', online: true);

    final empty = controllerFor(
      repository: DeterministicFakeOfficerReportRepository(
        report: emptyReport(),
      ),
    );
    await empty.applyFreshPrincipal(
      principalId: 'empty-principal',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await empty.loadSingleGame('empty', online: true);

    final cache = InMemoryPrincipalOfficerReportCache();
    await cache.write(
      'offline-principal',
      DeterministicFakeOfficerReportRepository.fictionalReport,
    );
    final offline = controllerFor(cache: cache);
    await offline.applyFreshPrincipal(
      principalId: 'offline-principal',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await offline.loadSingleGame('fictional-game', online: false);

    for (final (controller, token) in [
      (ready, 'ready'),
      (empty, 'empty'),
      (offline, 'offline_cached_readonly'),
    ]) {
      await tester.pumpWidget(
        MaterialApp(home: OfficerReportPanel(controller: controller)),
      );
      final projection =
          find.byKey(const ValueKey('debug-officer-report-projection'));
      expect(projection, findsOneWidget);
      expect(
        tester.widget<Semantics>(projection).properties.label,
        '偵錯報表投影：$token；已啟用寫入控制：0',
      );
      expect(find.byType(FilledButton), findsNothing);
      expect(find.byType(ElevatedButton), findsNothing);
      expect(find.byType(TextButton), findsNothing);
      expect(find.byType(IconButton), findsNothing);
    }
  });

  test('report diagnostic resolution fails closed', () {
    expect(
      DebugOfficerReportProjection.canonicalState(
        freshReady: false,
        freshEmpty: false,
        offlineCachedReadonly: false,
        enabledWriteControlCount: 0,
      ),
      isNull,
    );
    expect(
      DebugOfficerReportProjection.canonicalState(
        freshReady: true,
        freshEmpty: false,
        offlineCachedReadonly: true,
        enabledWriteControlCount: 0,
      ),
      isNull,
    );
    expect(
      DebugOfficerReportProjection.canonicalState(
        freshReady: true,
        freshEmpty: false,
        offlineCachedReadonly: false,
        enabledWriteControlCount: 1,
      ),
      isNull,
    );
  });

  testWidgets('direct state injection cannot claim report authority',
      (tester) async {
    final controller = controllerFor();
    await controller.applyFreshPrincipal(
      principalId: 'injected-principal',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    controller
      ..report = DeterministicFakeOfficerReportRepository.fictionalReport
      ..state = OfficerReportViewState.ready;
    await tester.pumpWidget(
      MaterialApp(home: OfficerReportPanel(controller: controller)),
    );
    expect(
      find.byKey(const ValueKey('debug-officer-report-projection')),
      findsNothing,
    );
  });

  testWidgets('debug gate and projection exclude sensitive report material',
      (tester) async {
    final controller = controllerFor();
    await controller.applyFreshPrincipal(
      principalId: 'sensitive-principal-id',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    await controller.loadSingleGame('fictional-game', online: true);

    await tester.pumpWidget(MaterialApp(
      home: OfficerReportPanel(
        controller: controller,
        diagnosticEnabled: false,
      ),
    ));
    expect(
      find.byKey(const ValueKey('debug-officer-report-projection')),
      findsNothing,
    );
    expect(
      DebugOfficerReportProjection.shouldRender(
        debugBuild: false,
        diagnosticEnabled: true,
      ),
      isFalse,
    );
    expect(
      DebugOfficerReportProjection.shouldRender(
        debugBuild: true,
        diagnosticEnabled: false,
      ),
      isFalse,
    );

    await tester.pumpWidget(
      MaterialApp(home: OfficerReportPanel(controller: controller)),
    );
    final projection =
        find.byKey(const ValueKey('debug-officer-report-projection'));
    final label = tester.widget<Semantics>(projection).properties.label!;
    for (final prohibited in [
      'sensitive-principal-id',
      'fictional-game',
      'fictional-replied',
      '已回覆隊員',
      'response_body',
      'officer-report-cache',
    ]) {
      expect(label, isNot(contains(prohibited)));
    }
  });

  testWidgets('all report states have distinguishable semantics', (
    tester,
  ) async {
    final controller = controllerFor();
    await controller.applyFreshPrincipal(
      principalId: 'read',
      reportReadGrant: const ManagementReportReadGrant.granted(),
    );
    controller.open(ManagementPresentationRoute.singleGameReport);
    for (final entry in <OfficerReportViewState, String>{
      OfficerReportViewState.loading: '報表載入中',
      OfficerReportViewState.empty: '此賽事目前沒有回覆資料',
      OfficerReportViewState.retryableError: '請重試',
      OfficerReportViewState.forbidden: '沒有報表讀取權限',
      OfficerReportViewState.sessionExpired: '登入已逾期',
      OfficerReportViewState.contractError: '資料格式異常',
    }.entries) {
      controller.state = entry.key;
      await tester.pumpWidget(
        MaterialApp(home: OfficerReportPanel(controller: controller)),
      );
      expect(
        tester
            .getSemantics(
              find.byKey(ValueKey('officer-report-${entry.key.name}')),
            )
            .label,
        contains(entry.value),
      );
    }
  });
}
