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
      {'person_id': 'person_1', 'display_name': '已出席', 'reply': 'attending'}
    ],
    'not_attending': [],
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

OfficerReportController controllerFor({
  OfficerReportPresentationPort? repository,
  InMemoryPrincipalOfficerReportCache? cache,
}) =>
    OfficerReportController(
      repository: repository ?? DeterministicFakeOfficerReportRepository(),
      cache: cache ?? InMemoryPrincipalOfficerReportCache(),
    );

void main() {
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
    expect(report.replied.single.displayName, '已出席');
    expect(report.notYetReplied.single.displayName, '尚未回覆');
  });

  test('server-owned grant maps Basic denied and Officer/Admin granted', () {
    for (final accessLevel in [AccessLevel.officer, AccessLevel.admin]) {
      final person = Person(
        'p',
        'Reader',
        const ['attendance:report:read'],
        accessLevel: accessLevel,
      );
      expect(person.canReadAttendanceReport, isTrue);
    }
    expect(
      const Person('p', 'Basic', ['games:read']).canReadAttendanceReport,
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
      expect(first.replied.single.displayName, '已回覆隊員');
      expect(first.notYetReplied.single.displayName, '尚未回覆隊員');
      expect(first.nonResponderInsight, isNotNull);
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
          report: const SingleGameReportUiModel(
            gameId: 'empty',
            gameLabel: '空白賽事',
            replied: [],
            notYetReplied: [],
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
    final transport = ReportTransport();
    final api = await reportApi(transport);
    await tester.pumpWidget(MaterialApp(
      home: CanonicalManagementReportsPage(
        api: api,
        person: const Person('basic', 'Basic', ['games:read']),
        games: [Game('game_44', DateTime.utc(2026), 60, null, 'A', 'B')],
        online: true,
      ),
    ));
    expect(find.byKey(const ValueKey('management-route-forbidden')),
        findsOneWidget);
    expect(find.text('唯讀出席報表'), findsNothing);
    expect(transport.calls, isEmpty);
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
    expect(find.text('已回覆'), findsOneWidget);
    expect(find.text('尚未回覆'), findsOneWidget);
    expect(find.text('高頻未回覆觀察'), findsOneWidget);
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
