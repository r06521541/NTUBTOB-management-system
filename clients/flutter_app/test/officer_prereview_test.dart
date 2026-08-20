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
      {'person_id': 'person_1', 'display_name': '已出席', 'reply': 'attending'}
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
    expect(report.attending.single.displayName, '已出席');
    expect(report.notAttending.single.displayName, '不出席');
    expect(report.notYetReplied.single.displayName, '尚未回覆');
    expect(report.notYetReplied.single.responseRate, 88);
    expect(report.historyGames, 8);
    expect(report.historyLimit, 12);
    expect(report.minimumResponseRate, 60);
    expect(report.generatedAt, DateTime.utc(2026, 8, 18, 12));
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
    expect(await restarted.read('officer', 'fictional-game'), isNotNull);
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
    expect(find.textContaining('回覆率 88%'), findsOneWidget);
    expect(find.text('觀察場次：8 / 12'), findsOneWidget);
    expect(find.text('最低回覆率：60%'), findsOneWidget);
    expect(find.textContaining('產生時間：2026-08-19'), findsOneWidget);
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
