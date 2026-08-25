import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/app_theme.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/foundation.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/main.dart' as entrypoint;
import 'package:ntubtob_portal/notification_center.dart';
import 'package:ntubtob_portal/officer_prereview.dart';

class _DelayedIndexStore extends MemoryStore {
  final aIndexStarted = Completer<void>();
  final releaseA = Completer<void>();

  @override
  Future<void> write(String key, String value) async {
    if (key == 'cache-index:v1:install' && value.startsWith('person-A:')) {
      if (!aIndexStarted.isCompleted) aIndexStarted.complete();
      await releaseA.future;
    }
    await super.write(key, value);
  }
}

class QueueTransport implements ApiTransport {
  final List<ApiResponse> responses = [];
  final List<(String, String, Map<String, String>, Map<String, dynamic>?)>
      calls = [];
  Completer<void>? mutationGate;
  Completer<void>? getGate;
  bool networkOnPut = false;
  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    calls.add((method, path, headers, body));
    if (method == 'GET' && getGate != null) {
      final gate = getGate!;
      getGate = null;
      await gate.future;
    }
    if (method == 'PUT' && networkOnPut) {
      networkOnPut = false;
      throw const NetworkException();
    }
    if (method == 'PUT' && mutationGate != null) {
      await mutationGate!.future;
    }
    return responses.removeAt(0);
  }
}

Map<String, dynamic> gameJson({
  int? durationMinutes = 60,
  String? location = '球場',
}) =>
    {
      'id': 'g',
      'start_at': '2026-08-18T12:00:00Z',
      'duration_minutes': durationMinutes,
      'location': location,
      'home_team': 'Home',
      'away_team': 'Away',
    };

Map<String, dynamic> eventJson({
  String id = 'event-1',
  String status = 'published',
}) =>
    {
      'id': id,
      'title': '移地訓練',
      'type': 'trip',
      'status': status,
      'start_at': '2026-09-01T01:00:00Z',
      'end_at': '2026-09-01T04:00:00Z',
      'activities': [
        {
          'id': 'activity-linked',
          'title': '友誼賽',
          'type': 'game',
          'position': 2,
          'start_at': '2026-09-01T02:00:00Z',
          'end_at': '2026-09-01T04:00:00Z',
          'linked_game_id': 'game-visible',
        },
        {
          'id': 'activity-hidden',
          'title': '另一場比賽',
          'type': 'game',
          'position': 1,
          'start_at': '2026-09-01T01:00:00Z',
          'end_at': '2026-09-01T01:30:00Z',
          'linked_game_id': 'game-not-visible',
        },
      ],
    };

Map<String, dynamic> attendanceJson({String? ownReply = 'undecided'}) => {
      'game_id': 'g',
      'own_reply': ownReply,
      'replied': [
        {
          'person_id': 'p2',
          'display_name': '已回覆隊員',
          'reply': 'attending',
          'qualification': 'team_player',
        },
      ],
    };

Map<String, dynamic> errorJson(String code) => {
      'error': {
        'code': code,
        'message': 'safe',
        'request_id': 'request',
        'retryable': false,
        'retry_after_seconds': null,
        'field_errors': [],
      },
    };

Map<String, dynamic> mutationJson() => {
      'game_id': 'g',
      'reply': 'attending',
      'changed': true,
      'updated_at': '2026-08-18T12:00:00Z',
      'notification': {'status': 'not_required', 'code': null},
      'idempotent_replay': false,
    };

Future<BasicApi> apiFor(QueueTransport transport, MemoryStore store) async {
  final session = SessionController(transport, store, 'install', SecureIds());
  await session.accept(
    const SessionEnvelope(
      accessToken: 'access',
      refreshToken: 'refresh-token-with-at-least-32-characters',
      sessionId: 's',
      expiresIn: 900,
    ),
  );
  return BasicApi(session, store, 'install', SecureIds());
}

class LogoutLine implements LineLoginPort {
  @override
  Future<String> login(String nonce) async => 'unused';

  @override
  Future<void> logout() async {}
}

Future<
    ({
      SessionController session,
      BasicCache basicCache,
      NotificationCache notificationCache,
      DurablePrincipalOfficerReportCache reportCache,
      BasicApi api,
    })> aggregateComponents(
  MemoryStore store, {
  String installationId = 'install',
  QueueTransport? transport,
}) async {
  final actualTransport = transport ?? QueueTransport();
  final notificationCache = NotificationCache(store, installationId);
  final session = SessionController(
    actualTransport,
    store,
    installationId,
    SecureIds(),
    terminalPurge: notificationCache.clear,
  );
  return (
    session: session,
    basicCache: BasicCache(store, installationId),
    notificationCache: notificationCache,
    reportCache: DurablePrincipalOfficerReportCache(store, installationId),
    api: BasicApi(session, store, installationId, SecureIds()),
  );
}

class PurgeFailingMemoryStore extends MemoryStore {
  @override
  Future<void> deleteKeysWithPrefix(String prefix) async {
    if (prefix.startsWith('mutation:install:')) {
      throw StateError('local purge failed');
    }
    await super.deleteKeysWithPrefix(prefix);
  }
}

class ObservationFailingMemoryStore extends MemoryStore {
  @override
  Future<int> countKeysWithPrefix(String prefix, {required int maximum}) async {
    throw StateError('storage observation failed');
  }
}

class FakePublishingClient implements NotificationPublishingClient {
  FakePublishingClient({this.confirmFailuresRemaining = 0});
  int confirmFailuresRemaining;
  final List<Map<String, dynamic>> previews = [];
  final List<Map<String, dynamic>> confirms = [];
  @override
  Future<Map<String, dynamic>> preview(Map<String, dynamic> draft) async {
    previews.add(draft);
    return {
      'draft': draft,
      'recipient_count': 2,
      'revision': List.filled(64, 'a').join(),
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
    if (confirmFailuresRemaining > 0) {
      confirmFailuresRemaining -= 1;
      throw StateError('fictional uncertain response');
    }
    return {
      'notification_id': 'notification_81',
      'recipient_count': 2,
      'deliveries': const [
        {'channel': 'in_app', 'status': 'succeeded', 'retryable': false},
        {'channel': 'push', 'status': 'pending', 'retryable': true},
      ],
      'idempotent_replay': false,
    };
  }
}

class DestinationNotificationClient implements NotificationClient {
  DestinationNotificationClient(this.values);

  List<MobileNotification> values;
  int detailReads = 0;
  int listReads = 0;
  int readMutations = 0;

  @override
  Future<MobileNotification> notification(String id) async {
    detailReads++;
    return values.singleWhere((item) => item.id == id);
  }

  @override
  Future<List<MobileNotification>> notifications(
      {bool unreadOnly = false}) async {
    listReads++;
    return values;
  }

  @override
  Future<int> unreadCount() async =>
      values.where((item) => !item.isRead).length;

  @override
  Future<NotificationReadResult> markRead(String id) async {
    readMutations++;
    final readAt = DateTime.utc(2026, 8, 22, 12);
    values = [
      for (final item in values)
        if (item.id == id) item.markRead(readAt) else item
    ];
    return NotificationReadResult(id, readAt, true);
  }

  @override
  Future<NotificationReadAllResult> markAllRead() async =>
      const NotificationReadAllResult(0, 0);
}

MobileNotification destinationNotification(Map<String, dynamic> destination) =>
    MobileNotification.fromJson({
      'id': 'notification_147',
      'type': 'game_change',
      'title': '場地異動',
      'body': '比賽改到第二球場。',
      'created_at': '2026-08-22T11:00:00Z',
      'visible_until': '2026-11-20T11:00:00Z',
      'read_at': null,
      'destination': destination,
    });

void main() {
  test('pending review and unknown recovery are mutually exclusive', () {
    expect(
      shouldOfferIdentityRecovery(
          state: AuthViewState.identityPending,
          pendingReviewCredential: 'line-or-google-review-only'),
      isFalse,
    );
    expect(
      shouldOfferIdentityRecovery(
          state: AuthViewState.identityPending, pendingReviewCredential: null),
      isTrue,
    );
    expect(
      shouldOfferIdentityRecovery(
          state: AuthViewState.loggedOut, pendingReviewCredential: null),
      isFalse,
    );
  });

  test('auth operation context rejects terminal epoch and person races', () {
    const operation = AuthOperationContext(4, 'person-A');
    expect(operation.matches(currentEpoch: 4, currentPersonId: 'person-A'),
        isTrue);
    expect(operation.matches(currentEpoch: 5, currentPersonId: 'person-A'),
        isFalse);
    expect(operation.matches(currentEpoch: 4, currentPersonId: 'person-B'),
        isFalse);
    expect(operation.matches(currentEpoch: 5, currentPersonId: null), isFalse);
  });

  test('fenced basic cache cannot let delayed A replace completed B', () async {
    final store = _DelayedIndexStore();
    final cache = BasicCache(store, 'install');
    var generation = 1;
    final a = cache.saveFenced(
      const Person('person-A', 'A', ['games:read']),
      const [],
      DateTime.utc(2026),
      generation: 1,
      isCurrent: () => generation == 1,
    );
    await store.aIndexStarted.future;
    generation = 2;
    await cache.saveFenced(
      const Person('person-B', 'B', ['games:read']),
      const [],
      DateTime.utc(2026, 1, 2),
      generation: 2,
      isCurrent: () => generation == 2,
    );
    store.releaseA.complete();
    expect(await a, isFalse);
    expect((await cache.load())!.person.id, 'person-B');
    expect(store.values.keys.any((key) => key.contains('person-A')), isFalse);
  });

  testWidgets('terminal profile mutation invokes canonical route reset',
      (tester) async {
    final transport = QueueTransport()
      ..responses.addAll([
        const ApiResponse(401, null),
        const ApiResponse(401, null),
      ]);
    final store = MemoryStore();
    final sessions =
        SessionController(transport, store, 'install', SecureIds());
    await sessions.accept(const SessionEnvelope(
      accessToken: 'access',
      refreshToken: 'refresh-token-with-at-least-32-characters',
      sessionId: 'session',
      expiresIn: 900,
    ));
    final api = BasicApi(sessions, store, 'install', SecureIds());
    var terminals = 0;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
          builder: (rootContext) => Scaffold(
                body: FilledButton(
                  onPressed: () =>
                      Navigator.of(rootContext).push(MaterialPageRoute<void>(
                    builder: (_) => DisplayNamePage(
                      api: api,
                      person: const Person('person-A', 'A', ['games:read']),
                      onTerminalSession: () async {
                        terminals++;
                        Navigator.of(rootContext)
                            .popUntil((route) => route.isFirst);
                      },
                    ),
                  )),
                  child: const Text('open'),
                ),
              )),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Updated');
    await tester.tap(find.byType(FilledButton));
    await tester.pumpAndSettle();
    expect(terminals, 1);
    expect(find.byType(DisplayNamePage), findsNothing);
    expect(await sessions.observePresence(), isFalse);
  });
  test('app theme reserves the global primary for team navy', () {
    expect(appBrandNavy, const Color(0xff29415d));
    final primary = appTheme(Brightness.light).colorScheme.primary;
    expect(primary.b, greaterThan(primary.g));
    expect(primary.b, greaterThan(primary.r));
  });

  for (final state in AuthViewState.values) {
    testWidgets('$state has distinguishable semantics', (tester) async {
      await tester.pumpWidget(MaterialApp(home: AuthStatePanel(state: state)));
      expect(find.bySemanticsLabel(RegExp('.+')), findsWidgets);
      if (state == AuthViewState.booting || state == AuthViewState.exchanging) {
        expect(find.byType(CircularProgressIndicator), findsOneWidget);
      }
    });
  }

  testWidgets('unresolved native timeout hides login action', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AuthStatePanel(state: AuthViewState.timeoutUnresolved),
          floatingActionButton: LoginActionButton(
            state: AuthViewState.timeoutUnresolved,
            onLogin: null,
          ),
        ),
      ),
    );
    expect(find.text('LINE 登入已逾時，請關閉既有登入畫面後返回'), findsOneWidget);
    expect(find.byTooltip('LINE 登入'), findsNothing);
  });

  testWidgets('confirmed cancellation re-enables one login action', (
    tester,
  ) async {
    var calls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          floatingActionButton: LoginActionButton(
            state: AuthViewState.cancelled,
            onLogin: () => calls++,
          ),
        ),
      ),
    );
    expect(find.byTooltip('LINE 登入'), findsOneWidget);
    await tester.tap(find.byTooltip('LINE 登入'));
    expect(calls, 1);
  });

  test('fake versus real composition selects separate roots', () {
    final fake = entrypoint.composeRoot(
      AppConfig.parse(flavor: 'development', mode: 'fake'),
    );
    final real = entrypoint.composeRoot(
      AppConfig.parse(
        flavor: 'staging',
        mode: 'real',
        apiBaseUrl: 'https://example.invalid',
        lineChannelId: '123',
        googleClientId: 'fixture-ios.apps.googleusercontent.com',
        googleServerClientId: 'fixture-web.apps.googleusercontent.com',
      ),
    );
    expect(fake, isA<DemoApp>());
    expect(real, isA<BasicBootstrapApp>());
  });

  test('only recoverable network plus cache becomes offline', () {
    expect(
      classifyFailure(const NetworkException(), hasCache: true),
      AuthViewState.offline,
    );
    expect(
      classifyFailure(const NetworkException(), hasCache: false),
      AuthViewState.recoverableError,
    );
    expect(
      classifyFailure(const ContractException('bad'), hasCache: true),
      AuthViewState.contractError,
    );
    expect(
      classifyFailure(const SessionExpiredException(), hasCache: true),
      AuthViewState.sessionExpired,
    );
  });

  test('pending Basic reload disables terminal logout', () {
    expect(
      canStartLogout(AuthViewState.authenticated, basicLoadInProgress: false),
      isTrue,
    );
    expect(
      canStartLogout(AuthViewState.authenticated, basicLoadInProgress: true),
      isFalse,
    );
    expect(
      canStartLogout(AuthViewState.offline, basicLoadInProgress: false),
      isFalse,
    );
  });

  test(
    'retained logout callback cannot cross a pending Basic reload',
    () async {
      var logoutCalls = 0;
      Future<void> logout() async => logoutCalls++;

      await runBasicLogoutIfAllowed(
        state: AuthViewState.authenticated,
        basicLoadInProgress: true,
        logout: logout,
      );
      expect(logoutCalls, 0);

      await runBasicLogoutIfAllowed(
        state: AuthViewState.authenticated,
        basicLoadInProgress: false,
        logout: logout,
      );
      expect(logoutCalls, 1);
    },
  );

  test('native platform mapping accepts only Android and iOS', () {
    expect(nativePlatformName(TargetPlatform.android), 'android');
    expect(nativePlatformName(TargetPlatform.iOS), 'ios');
    expect(nativePlatformName(TargetPlatform.windows), isNull);
    expect(nativePlatformName(TargetPlatform.linux), isNull);
    expect(nativePlatformName(TargetPlatform.macOS), isNull);
    expect(nativePlatformName(TargetPlatform.fuchsia), isNull);
  });

  testWidgets(
      'real Basic composition opens loaded notification detail without fetch',
      (tester) async {
    final item = destinationNotification({
      'type': 'notification',
      'notification_id': 'notification_147',
    });
    final client = DestinationNotificationClient([item]);
    final controller = NotificationCenterController(
      client: client,
      cache: NotificationCache(MemoryStore(), 'install'),
      principal: const Person('p', 'Basic', ['notifications:read']),
    );
    await controller.load(online: true);
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(MaterialApp(
      home: BasicGamesView(
        api: api,
        person: controller.principal,
        games: const [],
        online: true,
        lastSyncedAt: DateTime.utc(2026),
        notificationController: controller,
      ),
    ));

    await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('場地異動'));
    await tester.pumpAndSettle();

    expect(find.byType(NotificationDetailPage), findsOneWidget);
    expect(find.text('比賽改到第二球場。'), findsOneWidget);
    expect(client.detailReads, 0);
    expect(client.readMutations, 1);
  });

  testWidgets('unauthorized game destination stays in centre without I/O',
      (tester) async {
    final item = destinationNotification({
      'type': 'game',
      'game_id': 'game_147',
    });
    final client = DestinationNotificationClient([item]);
    final controller = NotificationCenterController(
      client: client,
      cache: NotificationCache(MemoryStore(), 'install'),
      principal: const Person('p', 'Basic', ['notifications:read']),
    );
    await controller.load(online: true);
    final transport = QueueTransport();
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(MaterialApp(
      home: BasicGamesView(
        api: api,
        person: controller.principal,
        games: const [],
        online: true,
        lastSyncedAt: DateTime.utc(2026),
        notificationController: controller,
      ),
    ));

    await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('場地異動'));
    await tester.pump();

    expect(find.byType(NotificationCenter), findsOneWidget);
    expect(find.text('找不到可查看的賽事，仍停留在通知中心。'), findsOneWidget);
    expect(transport.calls, isEmpty);
    expect(client.detailReads, 0);
  });

  testWidgets(
      'offline authorized game destination opens cached read-only detail',
      (tester) async {
    final item = destinationNotification({
      'type': 'game',
      'game_id': 'game_147',
    });
    final cache = NotificationCache(MemoryStore(), 'install');
    const person = Person('p', 'Basic', ['notifications:read']);
    await cache.save(person, [item], DateTime.utc(2026, 8, 22));
    final client = DestinationNotificationClient([item]);
    final controller = NotificationCenterController(
      client: client,
      cache: cache,
      principal: person,
      clock: () => DateTime.utc(2026, 8, 22, 12),
    );
    await controller.load(online: false);
    final transport = QueueTransport();
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(MaterialApp(
      home: BasicGamesView(
        api: api,
        person: person,
        games: [
          Game('game_147', DateTime.utc(2026, 9), 60, null, 'Home', 'Away')
        ],
        online: false,
        lastSyncedAt: DateTime.utc(2026),
        notificationController: controller,
      ),
    ));

    await tester.tap(find.byKey(const ValueKey('notification-center-entry')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('場地異動'));
    await tester.pumpAndSettle();

    expect(find.byType(CachedGameDetailPage), findsOneWidget);
    expect(find.text('離線快取賽事，僅供查看。'), findsOneWidget);
    expect(transport.calls, isEmpty);
    expect(client.readMutations, 0);
  });

  testWidgets('Basic-only navigation exposes games and no management', (
    tester,
  ) async {
    final transport = QueueTransport();
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: [Game('g', DateTime.utc(2026), 60, null, 'Home', 'Away')],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('game-g')),
      100,
    );
    expect(find.byKey(const ValueKey('game-g')), findsOneWidget);
    expect(find.text('管理'), findsNothing);
    expect(find.text('系統公告'), findsNothing);
  });

  testWidgets('events capability gates entry and offline performs zero reads', (
    tester,
  ) async {
    final transport = QueueTransport();
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(MaterialApp(
      home: BasicGamesView(
        api: api,
        person: const Person('p', 'Basic', ['games:read']),
        games: const [],
        online: true,
        lastSyncedAt: DateTime.utc(2026),
      ),
    ));
    expect(find.byKey(const ValueKey('events-entry')), findsNothing);

    await tester.pumpWidget(MaterialApp(
      home: BasicGamesView(
        api: api,
        person: const Person('p', 'Basic', ['games:read', 'events:read']),
        games: const [],
        online: false,
        lastSyncedAt: DateTime.utc(2026),
      ),
    ));
    await tester.scrollUntilVisible(
        find.byKey(const ValueKey('events-entry')), 100);
    await tester.tap(find.byKey(const ValueKey('events-entry')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('events-offline-unavailable')),
        findsOneWidget);
    expect(transport.calls, isEmpty);
  });

  testWidgets(
      'event list shows loading and cancelled detail with scoped game links', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final gate = Completer<void>();
    final transport = QueueTransport()
      ..getGate = gate
      ..responses.addAll([
        ApiResponse(200, {
          'items': [eventJson(status: 'cancelled')],
          'next_cursor': null,
        }),
        ApiResponse(200, eventJson(status: 'cancelled')),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(MaterialApp(
      home: EventListPage(
        api: api,
        online: true,
        visibleGames: [
          Game('game-visible', DateTime.utc(2026, 9, 1, 2), 120, null,
              'Home', 'Away'),
        ],
      ),
    ));
    expect(find.byKey(const ValueKey('events-loading')), findsOneWidget);
    gate.complete();
    await tester.pumpAndSettle();
    expect(find.textContaining('已取消'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('event-event-1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('event-cancelled')), findsOneWidget);
  });

  test('event linked game resolves only inside the visible game scope', () {
    final visible = [
      Game('game-visible', DateTime.utc(2026, 9, 1, 2), 120, null, 'Home',
          'Away'),
    ];
    expect(visibleLinkedGame('game-visible', visible)?.id, 'game-visible');
    expect(visibleLinkedGame('game-not-visible', visible), isNull);
    expect(visibleLinkedGame(null, visible), isNull);
  });

  testWidgets('event list distinguishes empty and recoverable error', (
    tester,
  ) async {
    final emptyTransport = QueueTransport()
      ..responses.add(const ApiResponse(200, {
        'items': <dynamic>[],
        'next_cursor': null,
      }));
    await tester.pumpWidget(MaterialApp(
      home: EventListPage(
        api: await apiFor(emptyTransport, MemoryStore()),
        online: true,
        visibleGames: const [],
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('events-empty')), findsOneWidget);

    final errorTransport = QueueTransport()
      ..responses.add(ApiResponse(503, errorJson('service_unavailable')));
    await tester.pumpWidget(MaterialApp(
      home: EventListPage(
        key: UniqueKey(),
        api: await apiFor(errorTransport, MemoryStore()),
        online: true,
        visibleGames: const [],
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('events-error')), findsOneWidget);
    expect(find.byKey(const ValueKey('events-retry')), findsOneWidget);
  });

  testWidgets('fresh account status is reachable with safe semantics', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person(
              'hidden-id',
              '可見名稱',
              [
                'hidden-capability',
              ],
              accessLevel: AccessLevel.admin),
          games: const [],
          online: true,
          lastSyncedAt: DateTime.utc(2026, 8, 20, 1, 2),
          principalProvenance: PrincipalProvenance.freshServer,
        ),
      ),
    );

    await tester.tap(find.byKey(const ValueKey('account-data-status-entry')));
    await tester.pumpAndSettle();
    expect(find.text('帳號與資料狀態'), findsOneWidget);
    expect(find.text('可見名稱'), findsOneWidget);
    expect(find.textContaining('伺服器同步資料'), findsWidgets);
    expect(find.byKey(const ValueKey('management-report-entry')), findsNothing);
    expect(api.session.api, isA<QueueTransport>());
    expect((api.session.api as QueueTransport).calls, isEmpty);
    final semantics = tester.getSemantics(
      find.byKey(const ValueKey('account-data-provenance')),
    );
    expect(semantics.label, contains('伺服器同步資料'));
    final renderedText = tester
        .widgetList<Text>(
          find.descendant(
            of: find.byType(AccountDataStatusPage),
            matching: find.byType(Text),
          ),
        )
        .map((text) => text.data ?? text.textSpan?.toPlainText() ?? '')
        .join('\n');
    final pageSemantics = [
      tester.getSemantics(find.byKey(const ValueKey('account-display-name'))),
      tester.getSemantics(find.byKey(const ValueKey('account-last-sync'))),
      semantics,
    ].map((node) => node.label).join('\n');
    for (final sensitive in [
      'hidden-id',
      'hidden-capability',
      'admin',
      'access',
      'token',
      'session',
      'endpoint',
      'cache',
      'fresh_server',
      'offline_cache',
    ]) {
      expect(renderedText, isNot(contains(sensitive)));
      expect(pageSemantics, isNot(contains(sensitive)));
      expect(semantics.label, isNot(contains(sensitive)));
    }
  });

  testWidgets('support and app information is reachable without transport', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('person-id', '名稱', ['games:read']),
          games: const [],
          online: true,
          lastSyncedAt: DateTime.utc(2026, 8, 20),
          principalProvenance: PrincipalProvenance.freshServer,
        ),
      ),
    );

    await tester.tap(find.byKey(const ValueKey('support-app-info-entry')));
    await tester.pumpAndSettle();

    expect(find.text('支援與 App 資訊'), findsOneWidget);
    expect(find.text('未提供'), findsNWidgets(2));
    expect((api.session.api as QueueTransport).calls, isEmpty);
  });

  testWidgets('offline account status is read-only and non-authoritative', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('offline-id', '離線名稱', ['games:read']),
          games: const [],
          online: false,
          lastSyncedAt: DateTime.utc(2026, 8, 20),
          principalProvenance: PrincipalProvenance.offlineCache,
        ),
      ),
    );

    await tester.tap(find.byKey(const ValueKey('account-data-status-entry')));
    await tester.pumpAndSettle();
    final semantics = tester.getSemantics(
      find.byKey(const ValueKey('account-data-provenance')),
    );
    expect(semantics.label, contains('離線快取'));
    expect(semantics.label, contains('唯讀'));
    expect(semantics.label, contains('非權威'));
    expect(find.byTooltip('重新整理賽事'), findsNothing);
    expect(find.text('出席報表'), findsNothing);
    expect((api.session.api as QueueTransport).calls, isEmpty);
  });

  testWidgets(
    'unknown account provenance fails closed without internal labels',
    (tester) async {
      final transport = QueueTransport();
      final api = await apiFor(transport, MemoryStore());
      await tester.pumpWidget(
        MaterialApp(
          home: BasicGamesView(
            api: api,
            person: const Person('unknown-id', '未知來源名稱', ['games:read']),
            games: const [],
            online: true,
            lastSyncedAt: DateTime.utc(2026, 8, 20),
          ),
        ),
      );

      await tester.tap(find.byKey(const ValueKey('account-data-status-entry')));
      await tester.pumpAndSettle();
      final semantics = tester.getSemantics(
        find.byKey(const ValueKey('account-data-provenance')),
      );
      expect(semantics.label, contains('資料來源未確認，請勿視為權威'));
      expect(semantics.label, isNot(contains('fresh_server')));
      expect(semantics.label, isNot(contains('offline_cache')));
      expect(transport.calls, isEmpty);
    },
  );

  testWidgets('debug projection localizes every role and report-read state', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    final cases = <(AccessLevel, bool, String)>[
      (AccessLevel.basic, false, '一般使用者'),
      (AccessLevel.basic, true, '一般使用者'),
      (AccessLevel.officer, false, '幹部'),
      (AccessLevel.officer, true, '幹部'),
      (AccessLevel.admin, false, '系統管理者'),
      (AccessLevel.admin, true, '系統管理者'),
    ];
    for (final (accessLevel, enabled, role) in cases) {
      await tester.pumpWidget(
        MaterialApp(
          home: BasicGamesView(
            api: api,
            person: Person(
              'p',
              'Visible elsewhere',
              enabled ? const ['attendance:report:read'] : const [],
              accessLevel: accessLevel,
            ),
            games: const [],
            online: true,
            lastSyncedAt: DateTime.utc(2026),
            principalProvenance: PrincipalProvenance.freshServer,
            diagnosticEnabled: true,
          ),
        ),
      );
      final projection = find.byKey(
        const ValueKey('debug-principal-projection'),
      );
      expect(projection, findsOneWidget);
      expect(
        tester.getSemantics(projection).label,
        contains(
          '偵錯權限投影：$role；報表讀取：${enabled && accessLevel != AccessLevel.basic ? '啟用' : '停用'}；來源：fresh_server（伺服器最新驗證）',
        ),
      );
      expect(find.text('attendance:report:read'), findsNothing);
      expect(find.text('p'), findsNothing);
    }
  });

  testWidgets('fresh Basic and Officer projections are authoritative', (
    tester,
  ) async {
    final cases = <(Person, String)>[
      (
        const Person('basic-id', 'Basic', ['games:read']),
        '偵錯權限投影：一般使用者；報表讀取：停用；來源：fresh_server（伺服器最新驗證）',
      ),
      (
        const Person(
            'officer-id',
            'Officer',
            [
              'attendance:report:read',
            ],
            accessLevel: AccessLevel.officer),
        '偵錯權限投影：幹部；報表讀取：啟用；來源：fresh_server（伺服器最新驗證）',
      ),
    ];

    for (final (person, expectedLabel) in cases) {
      await tester.pumpWidget(
        MaterialApp(
          home: Material(
            child: DebugPrincipalProjection(
              person: person,
              provenance: PrincipalProvenance.freshServer,
            ),
          ),
        ),
      );
      final projection = find.byKey(
        const ValueKey('debug-principal-projection'),
      );
      expect(
        tester.widget<Semantics>(projection).properties.label,
        expectedLabel,
      );
    }
  });

  testWidgets('offline cached Officer is explicitly non-authoritative', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person(
              'cached-id',
              'Cached Officer',
              [
                'attendance:report:read',
              ],
              accessLevel: AccessLevel.officer),
          games: const [],
          online: false,
          lastSyncedAt: DateTime.utc(2026),
          principalProvenance: PrincipalProvenance.offlineCache,
        ),
      ),
    );

    final projection = find.byKey(const ValueKey('debug-principal-projection'));
    final label = tester.getSemantics(projection).label;
    expect(label, contains('報表讀取：啟用'));
    expect(label, contains('來源：offline_cache（離線快取，非權威）'));
    expect(label, isNot(contains('fresh_server')));
    expect(
      find.byKey(const ValueKey('management-report-entry')),
      findsOneWidget,
    );
  });

  testWidgets('direct widget injection without provenance fails closed', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person(
              'injected-id',
              'Injected Officer',
              [
                'attendance:report:read',
              ],
              accessLevel: AccessLevel.officer),
          games: const [],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );

    final projection = find.byKey(const ValueKey('debug-principal-projection'));
    final label = tester.getSemantics(projection).label;
    expect(label, contains('來源：unknown（來源未確認，非權威）'));
    expect(label, isNot(contains('fresh_server')));
  });

  testWidgets('debug projection excludes sensitive principal material', (
    tester,
  ) async {
    const sensitive = [
      'person-sensitive-id',
      'Sensitive Display Name',
      'raw:capability',
      'token-sensitive',
      'origin-sensitive',
      'body-sensitive',
      'storage-sensitive',
    ];
    await tester.pumpWidget(
      MaterialApp(
        home: Material(
          child: DebugPrincipalProjection(
            person: Person(
                sensitive[0],
                sensitive[1],
                [
                  sensitive[2],
                  sensitive[3],
                ],
                accessLevel: AccessLevel.officer),
            provenance: PrincipalProvenance.offlineCache,
          ),
        ),
      ),
    );

    final projection = find.byKey(const ValueKey('debug-principal-projection'));
    final label = tester.getSemantics(projection).label;
    for (final value in sensitive) {
      expect(label, isNot(contains(value)));
    }
  });

  testWidgets(
    'release-mode hard gate hides projection without changing guard',
    (tester) async {
      final api = await apiFor(QueueTransport(), MemoryStore());
      const person = Person(
          'p',
          'Officer',
          [
            'attendance:report:read',
          ],
          accessLevel: AccessLevel.officer);
      await tester.pumpWidget(
        MaterialApp(
          home: BasicGamesView(
            api: api,
            person: person,
            games: const [],
            online: true,
            lastSyncedAt: DateTime.utc(2026),
            diagnosticEnabled: false,
          ),
        ),
      );
      expect(
        find.byKey(const ValueKey('debug-principal-projection')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('management-report-entry')),
        findsOneWidget,
      );
    },
  );

  test('release hard gate cannot be overridden by an injected flag', () {
    expect(
      DebugPrincipalProjection.shouldRender(
        debugBuild: false,
        diagnosticEnabled: true,
      ),
      isFalse,
    );
    expect(
      DebugPrincipalProjection.shouldRender(
        debugBuild: true,
        diagnosticEnabled: false,
      ),
      isFalse,
    );
    expect(
      DebugPrincipalProjection.shouldRender(
        debugBuild: true,
        diagnosticEnabled: true,
      ),
      isTrue,
    );
  });

  testWidgets(
    'server report grant exposes only the read-only management route',
    (tester) async {
      final api = await apiFor(QueueTransport(), MemoryStore());
      await tester.pumpWidget(
        MaterialApp(
          home: BasicGamesView(
            api: api,
            person: const Person(
                'p',
                'Officer',
                [
                  'games:read',
                  'attendance:report:read',
                ],
                accessLevel: AccessLevel.officer),
            games: [Game('g', DateTime.utc(2026), 60, null, 'Home', 'Away')],
            online: true,
            lastSyncedAt: DateTime.utc(2026),
          ),
        ),
      );
      expect(
        find.byKey(const ValueKey('management-report-entry')),
        findsOneWidget,
      );
      expect(find.text('通知廣播'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('management-report-entry')));
      await tester.pumpAndSettle();
      expect(find.text('出席報表'), findsOneWidget);
      expect(find.text('唯讀出席報表'), findsOneWidget);
      expect(find.text('送出回覆'), findsNothing);
    },
  );

  testWidgets('Basic has no publishing route or recipient preview', (
    tester,
  ) async {
    final fake = FakePublishingClient();
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', [
            'games:read',
            'attendance:reply:self',
            'notifications:read',
          ]),
          games: const [],
          online: true,
          publishingClient: fake,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );
    expect(
      find.byKey(const ValueKey('notification-publishing-entry')),
      findsNothing,
    );
    expect(fake.previews, isEmpty);
  });

  testWidgets('authorized Officer previews typed count then confirms', (
    tester,
  ) async {
    final fake = FakePublishingClient();
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person(
              'p',
              'Officer',
              [
                'games:read',
                'attendance:reply:self',
                'notifications:read',
                'attendance:report:read',
                'notifications:publish',
              ],
              accessLevel: AccessLevel.officer),
          games: const [],
          online: true,
          publishingClient: fake,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );
    final entry = find.byKey(const ValueKey('notification-publishing-entry'));
    await tester.scrollUntilVisible(entry, 100);
    await tester.tap(entry);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('publishing-title')),
      '集合提醒',
    );
    await tester.enterText(
      find.byKey(const ValueKey('publishing-body')),
      '請準時抵達。',
    );
    await tester.tap(find.byKey(const ValueKey('publishing-preview')));
    await tester.pumpAndSettle();
    expect(find.text('預覽收件人：2 人'), findsOneWidget);
    expect(fake.previews.single['audience'], {'type': 'team'});
    await tester.enterText(
      find.byKey(const ValueKey('publishing-confirmation')),
      'PUBLISH 2',
    );
    await tester.pump();
    final confirm = find.byKey(const ValueKey('publishing-confirm'));
    await tester.ensureVisible(confirm);
    await tester.tap(confirm);
    await tester.pumpAndSettle();
    expect(fake.confirms, hasLength(1));
    expect(find.text('通知已保存；外部推播結果不影響 App 內通知紀錄'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('publishing-preview')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('publishing-confirmation')),
      'PUBLISH 2',
    );
    await tester.pump();
    final secondConfirm = find.byKey(const ValueKey('publishing-confirm'));
    await tester.ensureVisible(secondConfirm);
    await tester.tap(secondConfirm);
    await tester.pumpAndSettle();
    expect(fake.confirms, hasLength(2));
    expect(fake.confirms[1]['key'], isNot(fake.confirms[0]['key']));
  });

  testWidgets('uncertain publishing retry retains the random intent key', (
    tester,
  ) async {
    final fake = FakePublishingClient(confirmFailuresRemaining: 1);
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person(
              'p',
              'Officer',
              [
                'games:read',
                'attendance:reply:self',
                'notifications:read',
                'attendance:report:read',
                'notifications:publish',
              ],
              accessLevel: AccessLevel.officer),
          games: const [],
          online: true,
          publishingClient: fake,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );
    final entry = find.byKey(const ValueKey('notification-publishing-entry'));
    await tester.scrollUntilVisible(entry, 100);
    await tester.tap(entry);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('publishing-title')),
      '集合提醒',
    );
    await tester.enterText(
      find.byKey(const ValueKey('publishing-body')),
      '請準時抵達。',
    );
    await tester.tap(find.byKey(const ValueKey('publishing-preview')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('publishing-confirmation')),
      'PUBLISH 2',
    );
    await tester.pump();
    final confirm = find.byKey(const ValueKey('publishing-confirm'));
    await tester.ensureVisible(confirm);
    await tester.tap(confirm);
    await tester.pumpAndSettle();
    await tester.tap(confirm);
    await tester.pumpAndSettle();
    expect(fake.confirms, hasLength(2));
    expect(fake.confirms[1]['key'], fake.confirms[0]['key']);
  });

  testWidgets('offline Basic list disables detail and attendance reply', (
    tester,
  ) async {
    final transport = QueueTransport();
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: [Game('g', DateTime.utc(2026), 60, null, 'Home', 'Away')],
          online: false,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );
    final offline = find.byKey(const ValueKey('offline-read-only'));
    expect(offline, findsOneWidget);
    expect(tester.getSemantics(offline).label, contains('離線唯讀'));
    expect(
      tester
          .widget<IconButton>(find.byKey(const ValueKey('games-refresh')))
          .onPressed,
      isNull,
    );
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('game-g')),
      100,
    );
    await tester.tap(find.byKey(const ValueKey('game-g')));
    await tester.pump();
    expect(find.text('賽事與出席'), findsNothing);
    expect(transport.calls, isEmpty);
  });

  testWidgets('games are copy-safely chronological with readable details', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(800, 5000);
    addTearDown(tester.view.resetPhysicalSize);
    final api = await apiFor(QueueTransport(), MemoryStore());
    final games = [
      Game('late', DateTime.utc(2026, 8, 20, 12), 90, '晚場球館', 'H', 'A'),
      Game('early', DateTime.utc(2026, 8, 18, 12), 60, '早場球館', 'H', 'A'),
      Game('same-time', DateTime.utc(2026, 8, 18, 12), null, null, 'H', 'A'),
    ];
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: games,
          online: true,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );

    expect(games.map((game) => game.id), ['late', 'early', 'same-time']);
    final renderedIds = tester
        .widgetList<ListTile>(find.byType(ListTile))
        .map((tile) => (tile.key as ValueKey<String>?)?.value)
        .whereType<String>()
        .where((key) => key.startsWith('game-'))
        .toList();
    expect(renderedIds, ['game-early', 'game-same-time', 'game-late']);

    final earlySubtitle = tester
        .widget<Text>(
          find
              .descendant(
                of: find.byKey(const ValueKey('game-early')),
                matching: find.byType(Text),
              )
              .last,
        )
        .data!;
    expect(earlySubtitle, contains('早場球館'));
    expect(earlySubtitle, contains('60 分鐘'));
    expect(earlySubtitle, isNot(contains('2026-08-18T12:00:00.000Z')));
  });

  testWidgets('online refresh invokes one existing load while pending', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    final gate = Completer<void>();
    var refreshes = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: const [],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
          onRefresh: () async {
            refreshes++;
            await gate.future;
            return true;
          },
        ),
      ),
    );

    final refresh = find.byKey(const ValueKey('games-refresh'));
    await tester.tap(refresh);
    await tester.tap(refresh);
    await tester.pump();
    expect(refreshes, 1);
    expect(tester.widget<IconButton>(refresh).onPressed, isNull);

    gate.complete();
    await tester.pumpAndSettle();
    expect(tester.widget<IconButton>(refresh).onPressed, isNotNull);
  });

  testWidgets('online non-empty list pulls to invoke existing refresh once', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    var refreshes = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: [Game('g', DateTime.utc(2026), 60, null, 'Home', 'Away')],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
          onRefresh: () async {
            refreshes++;
            return true;
          },
        ),
      ),
    );

    final pullRefresh = tester.widget<RefreshIndicator>(
      find.byKey(const ValueKey('games-pull-refresh')),
    );
    expect(pullRefresh.semanticsLabel, '下拉重新整理賽事');
    await tester.fling(find.byType(ListView), const Offset(0, 300), 1000);
    await tester.pumpAndSettle();
    expect(refreshes, 1);
  });

  testWidgets('online empty list remains pull-scrollable', (tester) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    var refreshes = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: const [],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
          onRefresh: () async {
            refreshes++;
            return true;
          },
        ),
      ),
    );

    final scrollable = tester.state<ScrollableState>(find.byType(Scrollable));
    expect(scrollable.position.physics, isA<AlwaysScrollableScrollPhysics>());
    await tester.fling(find.byType(ListView), const Offset(0, 300), 1000);
    await tester.pumpAndSettle();
    expect(refreshes, 1);
  });

  testWidgets('pending pull refresh rejects an overlapping gesture', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    final gate = Completer<void>();
    var refreshes = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: const [],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
          onRefresh: () async {
            refreshes++;
            await gate.future;
            return true;
          },
        ),
      ),
    );

    final list = find.byType(ListView);
    await tester.fling(list, const Offset(0, 300), 1000);
    await tester.pump();
    await tester.fling(list, const Offset(0, 300), 1000);
    await tester.pump();
    expect(refreshes, 1);

    gate.complete();
    await tester.pumpAndSettle();
  });

  testWidgets('offline list exposes no pull refresh or callback', (
    tester,
  ) async {
    final transport = QueueTransport();
    final api = await apiFor(transport, MemoryStore());
    var refreshes = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: const [],
          online: false,
          lastSyncedAt: DateTime.utc(2026),
          onRefresh: () async {
            refreshes++;
            return true;
          },
        ),
      ),
    );

    expect(find.byKey(const ValueKey('games-pull-refresh')), findsNothing);
    await tester.fling(find.byType(ListView), const Offset(0, 300), 1000);
    await tester.pumpAndSettle();
    expect(refreshes, 0);
    expect(transport.calls, isEmpty);
  });

  testWidgets('failed online refresh can be retried', (tester) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    var refreshes = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: const [],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
          onRefresh: () async {
            refreshes++;
            if (refreshes == 1) throw StateError('refresh failed');
            return true;
          },
        ),
      ),
    );

    final refresh = find.byKey(const ValueKey('games-refresh'));
    await tester.tap(refresh);
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(tester.widget<IconButton>(refresh).onPressed, isNotNull);
    expect(
      tester
          .getSemantics(find.byKey(const ValueKey('games-refresh-result')))
          .label,
      contains('重新整理失敗'),
    );

    await tester.tap(refresh);
    await tester.pumpAndSettle();
    expect(refreshes, 2);
  });

  testWidgets(
    'refresh reports progress and changes sync time only on success',
    (tester) async {
      final api = await apiFor(QueueTransport(), MemoryStore());
      var lastSyncedAt = DateTime.utc(2026, 8, 20, 1, 2);
      var shouldSucceed = false;
      late void Function(void Function()) update;

      await tester.pumpWidget(
        MaterialApp(
          home: StatefulBuilder(
            builder: (context, setState) {
              update = setState;
              return BasicGamesView(
                api: api,
                person: const Person('p', 'Basic', ['games:read']),
                games: const [],
                online: true,
                lastSyncedAt: lastSyncedAt,
                onRefresh: () async {
                  await Future<void>.delayed(const Duration(milliseconds: 1));
                  if (!shouldSucceed) return false;
                  update(() => lastSyncedAt = DateTime.utc(2026, 8, 21, 1, 2));
                  return true;
                },
              );
            },
          ),
        ),
      );

      final refresh = find.byKey(const ValueKey('games-refresh'));
      final initialSyncLabel = tester
          .getSemantics(find.byKey(const ValueKey('games-last-sync')))
          .label;
      await tester.tap(refresh);
      await tester.pump();
      expect(
        find.byKey(const ValueKey('games-refresh-progress')),
        findsOneWidget,
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .getSemantics(find.byKey(const ValueKey('games-refresh-result')))
            .label,
        contains('重新整理失敗'),
      );
      expect(
        tester
            .getSemantics(find.byKey(const ValueKey('games-last-sync')))
            .label,
        initialSyncLabel,
      );

      shouldSucceed = true;
      await tester.tap(refresh);
      await tester.pumpAndSettle();
      expect(
        tester
            .getSemantics(find.byKey(const ValueKey('games-last-sync')))
            .label,
        isNot(initialSyncLabel),
      );
      expect(
        tester
            .getSemantics(find.byKey(const ValueKey('games-refresh-result')))
            .label,
        contains('重新整理完成'),
      );
    },
  );

  testWidgets('successful pull refresh returns the games list to its top', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    final games = List.generate(
      24,
      (index) => Game(
        'game-$index',
        DateTime.utc(2026, 8, 1).add(Duration(days: index)),
        60,
        '球場',
        'Home',
        'Away',
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: games,
          online: true,
          lastSyncedAt: DateTime.utc(2026),
          onRefresh: () async => true,
        ),
      ),
    );

    final scrollable = tester.state<ScrollableState>(find.byType(Scrollable));
    scrollable.position.jumpTo(300);
    expect(scrollable.position.pixels, 300);

    final refresh = tester
        .state<RefreshIndicatorState>(
          find.byKey(const ValueKey('games-pull-refresh')),
        )
        .show();
    await tester.pumpAndSettle();
    await refresh;
    expect(scrollable.position.pixels, 0);
  });

  testWidgets('empty games has recognizable read-state semantics', (
    tester,
  ) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: api,
          person: const Person('p', 'Basic', ['games:read']),
          games: const [],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );
    final empty = find.byKey(const ValueKey('games-empty'));
    expect(empty, findsOneWidget);
    expect(tester.getSemantics(empty).label, contains('目前沒有可顯示的賽事'));
  });

  testWidgets('game detail reads attendance and exposes five reply controls', (
    tester,
  ) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(api: api, gameId: 'g'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('已回覆隊員'), findsNWidgets(2));
    expect(find.text('未回覆'), findsNothing);
    for (final reply in AttendanceReply.values) {
      expect(find.byKey(ValueKey('reply-${reply.wire}')), findsOneWidget);
    }
  });

  testWidgets('list and detail share readable localized game metadata', (
    tester,
  ) async {
    final listApi = await apiFor(QueueTransport(), MemoryStore());
    final game = Game(
      'g',
      DateTime.parse('2026-08-18T12:00:00Z'),
      60,
      '球場',
      'Home',
      'Away',
    );
    await tester.pumpWidget(
      MaterialApp(
        home: BasicGamesView(
          api: listApi,
          person: const Person('p', 'Basic', ['games:read']),
          games: [game],
          online: true,
          lastSyncedAt: DateTime.utc(2026),
        ),
      ),
    );
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('game-g')),
      100,
    );
    final listMetadata = tester
        .widget<Text>(
          find
              .descendant(
                of: find.byKey(const ValueKey('game-g')),
                matching: find.byType(Text),
              )
              .last,
        )
        .data;

    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
      ]);
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(
          api: await apiFor(transport, MemoryStore()),
          gameId: 'g',
        ),
      ),
    );
    await tester.pumpAndSettle();
    final detailMetadata = tester
        .widget<Text>(find.byKey(const ValueKey('game-detail-metadata')))
        .data;

    expect(detailMetadata, listMetadata);
    expect(detailMetadata, contains('球場'));
    expect(detailMetadata, contains('60 分鐘'));
    expect(detailMetadata, isNot(contains('2026-08-18T12:00:00.000Z')));
  });

  testWidgets('game detail omits absent optional metadata', (tester) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson(durationMinutes: null, location: null)),
        ApiResponse(200, attendanceJson()),
      ]);
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(
          api: await apiFor(transport, MemoryStore()),
          gameId: 'g',
        ),
      ),
    );
    await tester.pumpAndSettle();
    final metadata = tester
        .widget<Text>(find.byKey(const ValueKey('game-detail-metadata')))
        .data!;

    expect(metadata, isNot(contains('球場')));
    expect(metadata, isNot(contains('分鐘')));
    expect(metadata, isNot(contains('null')));
    expect(metadata, isNot(contains('2026-08-18T12:00:00.000Z')));
  });

  testWidgets('fresh GET projects every canonical authoritative own reply', (
    tester,
  ) async {
    for (final reply in AttendanceReply.values) {
      final transport = QueueTransport()
        ..responses.addAll([
          ApiResponse(200, gameJson()),
          ApiResponse(200, attendanceJson(ownReply: reply.wire)),
        ]);
      final api = await apiFor(transport, MemoryStore());
      await tester.pumpWidget(
        MaterialApp(
          home: GameDetailPage(
            key: ValueKey('detail-${reply.wire}'),
            api: api,
            gameId: 'g',
          ),
        ),
      );
      await tester.pumpAndSettle();

      final projection = find.byKey(
        const ValueKey('debug-authoritative-own-reply-projection'),
      );
      expect(projection, findsOneWidget);
      expect(
        tester.widget<Semantics>(projection).properties.label,
        '偵錯權威出席回覆：${reply.wire}；來源：fresh_server_get',
      );
    }
  });

  testWidgets('fresh GET projects authoritative not-yet-replied as none', (
    tester,
  ) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson(ownReply: null)),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(api: api, gameId: 'g'),
      ),
    );
    await tester.pumpAndSettle();

    final projection = find.byKey(
      const ValueKey('debug-authoritative-own-reply-projection'),
    );
    expect(projection, findsOneWidget);
    expect(
      tester.widget<Semantics>(projection).properties.label,
      '偵錯權威出席回覆：none；來源：fresh_server_get',
    );
  });

  testWidgets('local chip selection does not change authoritative projection', (
    tester,
  ) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(api: api, gameId: 'g'),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('reply-attending')));
    await tester.pump();
    final projection = find.byKey(
      const ValueKey('debug-authoritative-own-reply-projection'),
    );
    expect(
      tester.widget<Semantics>(projection).properties.label,
      '偵錯權威出席回覆：undecided；來源：fresh_server_get',
    );
    expect(
      tester
          .widget<ChoiceChip>(find.byKey(const ValueKey('reply-attending')))
          .selected,
      isTrue,
    );
  });

  testWidgets(
    'successful reply applies authoritative own reply over local selection',
    (tester) async {
      final transport = QueueTransport()
        ..responses.addAll([
          ApiResponse(200, gameJson()),
          ApiResponse(200, attendanceJson()),
          ApiResponse(200, mutationJson()),
          ApiResponse(200, {
            'game_id': 'g',
            'own_reply': 'not_attending',
            'replied': [],
          }),
        ]);
      final api = await apiFor(transport, MemoryStore());
      await tester.pumpWidget(
        MaterialApp(
          home: GameDetailPage(api: api, gameId: 'g'),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('reply-attending')));
      await tester.tap(find.text('送出回覆'));
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<ChoiceChip>(find.byKey(const ValueKey('reply-attending')))
            .selected,
        isFalse,
      );
      expect(
        tester
            .widget<ChoiceChip>(
              find.byKey(const ValueKey('reply-not_attending')),
            )
            .selected,
        isTrue,
      );
      expect(find.byKey(const ValueKey('mutation-uncertain')), findsNothing);
      final projection = find.byKey(
        const ValueKey('debug-authoritative-own-reply-projection'),
      );
      expect(
        tester.widget<Semantics>(projection).properties.label,
        '偵錯權威出席回覆：not_attending；來源：mutation_readback',
      );
    },
  );

  testWidgets('uncertain conflicting reply has recognizable UX', (
    tester,
  ) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
        ApiResponse(200, {
          'game_id': 'g',
          'own_reply': 'undecided',
          'replied': [],
        }),
      ]);
    final store = MemoryStore()
      ..values['mutation:install:g'] =
          '{"key":"same-key-value-1234","reply":"attending","uncertain":true}';
    final api = await apiFor(transport, store);
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(api: api, gameId: 'g'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reply-not_attending')));
    await tester.tap(find.text('送出回覆'));
    await tester.pumpAndSettle();
    final uncertain = find.byKey(const ValueKey('mutation-uncertain'));
    expect(uncertain, findsOneWidget);
    expect(tester.getSemantics(uncertain).label, contains('回覆結果待確認'));
    expect(
      find.byKey(const ValueKey('debug-authoritative-own-reply-projection')),
      findsNothing,
    );
  });

  testWidgets('PUT Network ambiguity displays uncertain instead of error', (
    tester,
  ) async {
    final transport = QueueTransport()
      ..networkOnPut = true
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
        ApiResponse(200, {'game_id': 'g', 'own_reply': null, 'replied': []}),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(api: api, gameId: 'g'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reply-attending')));
    await tester.tap(find.text('送出回覆'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('mutation-uncertain')), findsOneWidget);
    expect(find.byKey(const ValueKey('mutation-error')), findsNothing);
    expect(
      find.byKey(const ValueKey('debug-authoritative-own-reply-projection')),
      findsNothing,
    );
    expect(transport.calls.map((call) => call.$1), [
      'GET',
      'GET',
      'PUT',
      'GET',
    ]);
  });

  testWidgets('mutation pending disables submit then returns ready', (
    tester,
  ) async {
    final gate = Completer<void>();
    final transport = QueueTransport()
      ..mutationGate = gate
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
        ApiResponse(200, mutationJson()),
        ApiResponse(200, attendanceJson()),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(api: api, gameId: 'g'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reply-attending')));
    await tester.tap(find.text('送出回覆'));
    await tester.pump();
    expect(find.text('送出中'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('debug-authoritative-own-reply-projection')),
      findsNothing,
    );
    expect(
      tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
      isNull,
    );
    gate.complete();
    await tester.pumpAndSettle();
    expect(find.text('送出回覆'), findsOneWidget);
    expect(
      tester
          .widget<Semantics>(
            find.byKey(
              const ValueKey('debug-authoritative-own-reply-projection'),
            ),
          )
          .properties
          .label,
      '偵錯權威出席回覆：undecided；來源：mutation_readback',
    );
  });

  test('authoritative reply resolver fails closed', () {
    expect(
      DebugAuthoritativeOwnReplyProjection.canonicalReply(
        reply: AttendanceReply.attending,
        detailReady: true,
        freshServerGet: false,
        mutationReadback: false,
      ),
      isNull,
    );
    expect(
      DebugAuthoritativeOwnReplyProjection.canonicalReply(
        reply: AttendanceReply.attending,
        detailReady: true,
        freshServerGet: true,
        mutationReadback: true,
      ),
      isNull,
    );
    expect(
      DebugAuthoritativeOwnReplyProjection.canonicalReply(
        reply: AttendanceReply.attending,
        detailReady: false,
        freshServerGet: true,
        mutationReadback: false,
      ),
      isNull,
    );
    expect(
      DebugAuthoritativeOwnReplyProjection.canonicalReply(
        reply: null,
        detailReady: true,
        freshServerGet: true,
        mutationReadback: false,
      ),
      (
        CanonicalOwnReplyObservation.none,
        AuthoritativeOwnReplySource.freshServerGet,
      ),
    );
    expect(
      DebugAuthoritativeOwnReplyProjection.canonicalReply(
        reply: null,
        detailReady: true,
        freshServerGet: false,
        mutationReadback: false,
      ),
      isNull,
    );
  });

  testWidgets('reply diagnostic gate and output exclude sensitive material', (
    tester,
  ) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson(ownReply: 'attending')),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(
          api: api,
          gameId: 'sensitive-game-id',
          diagnosticEnabled: false,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('debug-authoritative-own-reply-projection')),
      findsNothing,
    );
    expect(
      DebugAuthoritativeOwnReplyProjection.shouldRender(
        debugBuild: false,
        diagnosticEnabled: true,
      ),
      isFalse,
    );
    expect(
      DebugAuthoritativeOwnReplyProjection.shouldRender(
        debugBuild: true,
        diagnosticEnabled: false,
      ),
      isFalse,
    );

    final visibleTransport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson(ownReply: 'attending')),
      ]);
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(
          api: await apiFor(visibleTransport, MemoryStore()),
          gameId: 'g',
        ),
      ),
    );
    await tester.pumpAndSettle();
    final projection = find.byKey(
      const ValueKey('debug-authoritative-own-reply-projection'),
    );
    final label = tester.widget<Semantics>(projection).properties.label!;
    for (final prohibited in [
      'sensitive-game-id',
      'p2',
      '已回覆隊員',
      'response_body',
      'same-key-value-1234',
      'access',
      'mutation:install:g',
    ]) {
      expect(label, isNot(contains(prohibited)));
    }
  });

  testWidgets('cache/session projection is bounded and release-gated', (
    tester,
  ) async {
    const aggregate = CacheSessionAggregate(
      sessionPresent: false,
      basicCachePresent: false,
      officerReportCachePresent: false,
      pendingAttendanceIntentPresent: false,
    );
    await tester.pumpWidget(
      const MaterialApp(
        home: DebugCacheSessionProjection(aggregate: aggregate),
      ),
    );
    final projection = find.byKey(
      const ValueKey('debug-cache-session-projection'),
    );
    final label = tester.widget<Semantics>(projection).properties.label!;
    expect(label, contains('session absent'));
    expect(label, contains('basic_cache absent'));
    expect(label, contains('officer_report_cache absent'));
    expect(label, contains('pending_attendance_intent absent'));
    for (final prohibited in [
      'refresh:install',
      'cache:v1',
      'officer-report-cache:v1',
      'mutation:install:g',
      'fictional-game',
      'access-token',
    ]) {
      expect(label, isNot(contains(prohibited)));
    }
    expect(
      DebugCacheSessionProjection.shouldRender(
        debugBuild: false,
        diagnosticEnabled: true,
      ),
      isFalse,
    );
    expect(
      DebugCacheSessionProjection.shouldRender(
        debugBuild: true,
        diagnosticEnabled: false,
      ),
      isFalse,
    );
  });

  testWidgets('real composition projects aggregate from physical storage', (
    tester,
  ) async {
    final store = MemoryStore()
      ..values['refresh:install'] = 'not-observed'
      ..values['cache-index:v1:install'] = 'not-output'
      ..values['cache:v1:install:person'] = 'not-observed'
      ..values['officer-report-cache:v1:install:person'] = 'not-observed'
      ..values['mutation:install:game'] = 'not-observed';
    final components = await aggregateComponents(store);
    final aggregate = await CacheSessionAggregateProducer.observe(
      session: components.session,
      basicCache: components.basicCache,
      reportCache: components.reportCache,
      api: components.api,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: DebugCacheSessionComposition(
          aggregate: aggregate,
          child: const Text('content'),
        ),
      ),
    );
    final projection = find.byKey(
      const ValueKey('debug-cache-session-projection'),
    );
    expect(projection, findsOneWidget);
    final label = tester.getSemantics(projection).label;
    expect(label, contains('session present'));
    expect(label, contains('basic_cache present'));
    expect(label, contains('officer_report_cache present'));
    expect(label, contains('pending_attendance_intent present'));
    expect(label, isNot(contains('person')));
    expect(label, isNot(contains('game')));
  });

  test('multiple physical pending intents fail closed before logout', () async {
    final store = MemoryStore()
      ..values['refresh:install'] = 'refresh'
      ..values['mutation:install:first'] = 'one'
      ..values['mutation:install:second'] = 'two';
    final components = await aggregateComponents(store);
    expect(
      await CacheSessionAggregateProducer.observe(
        session: components.session,
        basicCache: components.basicCache,
        reportCache: components.reportCache,
        api: components.api,
      ),
      isNull,
    );
  });

  testWidgets(
    'storage failure hides projection and cold logged-out is observable',
    (tester) async {
      final failingComponents = await aggregateComponents(
        ObservationFailingMemoryStore(),
      );
      final failed = await CacheSessionAggregateProducer.observe(
        session: failingComponents.session,
        basicCache: failingComponents.basicCache,
        reportCache: failingComponents.reportCache,
        api: failingComponents.api,
      );
      expect(failed, isNull);
      await tester.pumpWidget(
        MaterialApp(
          home: DebugCacheSessionComposition(
            aggregate: failed,
            child: const AuthStatePanel(state: AuthViewState.logoutPending),
          ),
        ),
      );
      expect(
        find.byKey(const ValueKey('debug-cache-session-projection')),
        findsNothing,
      );

      final coldComponents = await aggregateComponents(MemoryStore());
      final cold = await CacheSessionAggregateProducer.observe(
        session: coldComponents.session,
        basicCache: coldComponents.basicCache,
        reportCache: coldComponents.reportCache,
        api: coldComponents.api,
      );
      await tester.pumpWidget(
        MaterialApp(
          home: DebugCacheSessionComposition(
            aggregate: cold,
            child: const AuthStatePanel(state: AuthViewState.loggedOut),
          ),
        ),
      );
      final projection = find.byKey(
        const ValueKey('debug-cache-session-projection'),
      );
      expect(projection, findsOneWidget);
      expect(tester.getSemantics(projection).label, contains('session absent'));
      expect(
        tester.getSemantics(projection).label,
        contains('pending_attendance_intent absent'),
      );
    },
  );

  test(
    'fresh Basic downgrade physically removes Officer cache evidence',
    () async {
      final store = MemoryStore()..values['refresh:install'] = 'refresh';
      final components = await aggregateComponents(store);
      const previous = Person(
          'same',
          'Officer',
          [
            'attendance:report:read',
          ],
          accessLevel: AccessLevel.officer);
      const current = Person('same', 'Basic', ['games:read']);
      await components.basicCache.save(current, const [], DateTime.utc(2026));
      await components.reportCache.write(
        previous.id,
        DeterministicFakeOfficerReportRepository.fictionalReport,
      );
      await reconcileFreshReportPrincipal(
        cache: components.reportCache,
        previous: previous,
        current: current,
      );

      final aggregate = await CacheSessionAggregateProducer.observe(
        session: components.session,
        basicCache: components.basicCache,
        reportCache: components.reportCache,
        api: components.api,
      );
      expect(aggregate!.sessionPresent, isTrue);
      expect(aggregate.basicCachePresent, isTrue);
      expect(aggregate.officerReportCachePresent, isFalse);
      expect(aggregate.pendingAttendanceIntentPresent, isFalse);
    },
  );

  test(
    'terminal logout purges only current installation and observes absent',
    () async {
      final transport = QueueTransport()
        ..responses.add(const ApiResponse(204, null));
      final store = MemoryStore()..values['installation:v1'] = 'install';
      final components = await aggregateComponents(store, transport: transport);
      await components.session.accept(
        const SessionEnvelope(
          accessToken: 'access',
          refreshToken: 'refresh',
          sessionId: 'session',
          expiresIn: 900,
        ),
      );
      store.values['refresh-attempt:install'] = 'attempt';
      await components.basicCache.save(
        const Person('person', 'Basic', ['games:read']),
        const [],
        DateTime.utc(2026),
      );
      await components.reportCache.write(
        'person',
        DeterministicFakeOfficerReportRepository.fictionalReport,
      );
      store.values['mutation:install:first-game'] = 'intent';
      store.values['mutation:install:second-game'] = 'intent';
      await components.notificationCache.save(
        const Person('person', 'Basic', ['notifications:read']),
        const [],
        DateTime.utc(2026),
      );
      store.values['refresh:other'] = 'keep';
      store.values['refresh-attempt:other'] = 'keep';
      store.values['logout-pending:other'] = 'keep';
      store.values['cache-index:v1:other'] = 'other-person';
      store.values['cache:v1:other:other-person'] = 'keep';
      store.values['officer-report-cache:v1:other:other-person'] = 'keep';
      store.values['mutation:other:game'] = 'keep';
      store.values['notification-cache-index:v1:other'] = 'other-person';
      store.values['notification-cache:v1:other:other-person'] = 'keep';

      expect(
        await CacheSessionAggregateProducer.observe(
          session: components.session,
          basicCache: components.basicCache,
          reportCache: components.reportCache,
          api: components.api,
        ),
        isNull,
      );

      final aggregate = await completeTerminalLogout(
        session: components.session,
        basicCache: components.basicCache,
        notificationCache: components.notificationCache,
        reportCache: components.reportCache,
        api: components.api,
        line: LogoutLine(),
      );
      expect(
        aggregate,
        const CacheSessionAggregate(
          sessionPresent: false,
          basicCachePresent: false,
          officerReportCachePresent: false,
          pendingAttendanceIntentPresent: false,
        ),
      );
      expect(store.values['installation:v1'], 'install');
      expect(
        store.values.keys.where((key) => key.contains(':other')),
        hasLength(9),
      );
    },
  );

  testWidgets('purge failure stays fail closed with no projection', (
    tester,
  ) async {
    final transport = QueueTransport()
      ..responses.add(const ApiResponse(204, null));
    final store = PurgeFailingMemoryStore()
      ..values['mutation:install:game'] = 'intent';
    final components = await aggregateComponents(store, transport: transport);
    await components.session.accept(
      const SessionEnvelope(
        accessToken: 'access',
        refreshToken: 'refresh',
        sessionId: 'session',
        expiresIn: 900,
      ),
    );

    final aggregate = await completeTerminalLogout(
      session: components.session,
      basicCache: components.basicCache,
      notificationCache: components.notificationCache,
      reportCache: components.reportCache,
      api: components.api,
      line: LogoutLine(),
    );
    expect(aggregate, isNull);
    expect(store.values['logout-pending:install'], 'true');
    await tester.pumpWidget(
      MaterialApp(
        home: DebugCacheSessionComposition(
          aggregate: aggregate,
          child: const AuthStatePanel(state: AuthViewState.logoutPending),
        ),
      ),
    );
    expect(find.text('請使用 LINE 安全登入'), findsNothing);
    expect(
      find.byKey(const ValueKey('debug-cache-session-projection')),
      findsNothing,
    );
  });

  test('release gate cannot render a real aggregate when injected true', () {
    expect(
      DebugCacheSessionComposition.shouldRender(
        debugBuild: false,
        diagnosticEnabled: true,
        aggregatePresent: true,
      ),
      isFalse,
    );
  });

  testWidgets('canonical mutation error has fail-closed UX', (tester) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
        ApiResponse(409, errorJson('idempotency_conflict')),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(
      MaterialApp(
        home: GameDetailPage(api: api, gameId: 'g'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reply-attending')));
    await tester.tap(find.text('送出回覆'));
    await tester.pumpAndSettle();
    final error = find.byKey(const ValueKey('mutation-error'));
    expect(error, findsOneWidget);
    expect(tester.getSemantics(error).label, contains('出席回覆失敗'));
  });

  List<Game> actionGames(int count) => List.generate(
        count,
        (index) => Game(
          'action-$index',
          DateTime.utc(2026, 9, 1 + index),
          60,
          '場地 $index',
          '主隊 $index',
          '客隊 $index',
        ),
      );

  test('member action selects next five and defines pending truthfully',
      () async {
    final games = actionGames(7);
    final replies = <String, AttendanceReply?>{
      'action-0': null,
      'action-1': AttendanceReply.undecided,
      'action-2': AttendanceReply.attending,
      'action-3': AttendanceReply.notAttending,
      'action-4': AttendanceReply.arrivingLate,
    };
    final controller = MemberActionController(
      (id) async => AttendanceSnapshot(id, replies[id], const []),
      clock: () => DateTime.utc(2026, 8, 23),
    );
    await controller.load(principalScope: 'A', games: games, online: true);

    expect(controller.window.map((game) => game.id),
        ['action-0', 'action-1', 'action-2', 'action-3', 'action-4']);
    expect(controller.pending.map((game) => game.id), ['action-0', 'action-1']);
    expect(controller.nearestAction!.id, 'action-0');
    expect(controller.state, MemberActionState.actionable);
    expect(controller.message(online: true), contains('最近待處理'));
  });

  test('member action bounds concurrency and deduplicates in-flight reads',
      () async {
    final gates = <String, Completer<void>>{};
    final calls = <String, int>{};
    var active = 0;
    var maximumActive = 0;
    final controller = MemberActionController((id) async {
      calls[id] = (calls[id] ?? 0) + 1;
      active++;
      maximumActive = maximumActive < active ? active : maximumActive;
      final gate = gates.putIfAbsent(id, Completer<void>.new);
      await gate.future;
      active--;
      return AttendanceSnapshot(id, AttendanceReply.attending, const []);
    }, clock: () => DateTime.utc(2026, 8, 23));
    final games = actionGames(7);
    final first =
        controller.load(principalScope: 'A', games: games, online: true);
    final duplicate =
        controller.load(principalScope: 'A', games: games, online: true);
    await Future<void>.delayed(Duration.zero);
    expect(active, 3);
    for (final id in ['action-0', 'action-1', 'action-2']) {
      gates[id]!.complete();
    }
    await Future<void>.delayed(Duration.zero);
    for (final id in ['action-3', 'action-4']) {
      gates[id]!.complete();
    }
    await Future.wait([first, duplicate]);
    expect(maximumActive, 3);
    expect(calls.values, everyElement(1));
    expect(calls, hasLength(5));
  });

  test('offline unknown is not inferred pending and performs zero reads',
      () async {
    var reads = 0;
    final controller = MemberActionController((id) async {
      reads++;
      return AttendanceSnapshot(id, null, const []);
    }, clock: () => DateTime.utc(2026, 8, 23));
    await controller.load(
      principalScope: 'A',
      games: const [],
      online: false,
    );
    controller.remember('action-0', AttendanceReply.attending);
    await controller.load(
      principalScope: 'A',
      games: actionGames(3),
      online: false,
    );
    expect(reads, 0);
    expect(controller.pending, isEmpty);
    expect(controller.unknown, hasLength(2));
    expect(controller.state, MemberActionState.partialUnknown);
    expect(controller.message(online: false), contains('未知不列為待處理'));
  });

  test('member action principal switch clears same-game observations offline',
      () async {
    var reads = 0;
    final games = actionGames(1);
    final controller = MemberActionController((id) async {
      reads++;
      return AttendanceSnapshot(id, AttendanceReply.undecided, const []);
    }, clock: () => DateTime.utc(2026, 8, 23));
    await controller.load(principalScope: 'A', games: games, online: true);
    expect(controller.pending.single.id, 'action-0');

    await controller.load(principalScope: 'B', games: games, online: false);
    expect(reads, 1);
    expect(controller.pending, isEmpty);
    expect(controller.unknown.single.id, 'action-0');
    expect(controller.state, MemberActionState.partialUnknown);
  });

  test(
      'member action ignores stale online completion after offline window switch',
      () async {
    final gate = Completer<void>();
    var reads = 0;
    final controller = MemberActionController((id) async {
      reads++;
      await gate.future;
      return AttendanceSnapshot(id, AttendanceReply.undecided, const []);
    }, clock: () => DateTime.utc(2026, 8, 23));
    final oldLoad = controller.load(
      principalScope: 'A',
      games: actionGames(1),
      online: true,
    );
    await Future<void>.delayed(Duration.zero);
    final newWindow = [
      Game(
        'new-game',
        DateTime.utc(2026, 10, 1),
        60,
        '新場地',
        '新主隊',
        '新客隊',
      ),
    ];
    await controller.load(
      principalScope: 'A',
      games: newWindow,
      online: false,
    );
    gate.complete();
    await oldLoad;

    expect(reads, 1);
    expect(controller.window.single.id, 'new-game');
    expect(controller.pending, isEmpty);
    expect(controller.unknown.single.id, 'new-game');
    expect(controller.state, MemberActionState.partialUnknown);
  });

  testWidgets('action dashboard renders states and refreshes only opened game',
      (tester) async {
    final games = actionGames(2);
    final reads = <String>[];
    final controller = MemberActionController((id) async {
      reads.add(id);
      return AttendanceSnapshot(
        id,
        id == 'action-0' && reads.where((value) => value == id).length == 1
            ? AttendanceReply.undecided
            : AttendanceReply.attending,
        const [],
      );
    }, clock: () => DateTime.utc(2026, 8, 23));
    await controller.load(principalScope: 'A', games: games, online: true);
    final api = await apiFor(QueueTransport(), MemoryStore());
    var scheduleOpened = false;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: MemberActionHome(
          api: api,
          principalScope: 'A',
          games: games,
          online: true,
          controller: controller,
          onOpenGame: (_) async {},
          onOpenSchedule: () => scheduleOpened = true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(
        find.byKey(const ValueKey('action-home-actionable')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('action-home-open-nearest')));
    await tester.pumpAndSettle();
    expect(reads.where((id) => id == 'action-0'), hasLength(2));
    expect(reads.where((id) => id == 'action-1'), hasLength(1));
    expect(find.byKey(const ValueKey('action-home-resolved')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('action-home-schedule')));
    expect(scheduleOpened, isTrue);
  });

  testWidgets('action dashboard renders loading before observations settle',
      (tester) async {
    final gate = Completer<void>();
    final controller = MemberActionController((id) async {
      await gate.future;
      return AttendanceSnapshot(id, AttendanceReply.attending, const []);
    }, clock: () => DateTime.utc(2026, 8, 23));
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: MemberActionHome(
          api: api,
          principalScope: 'A',
          games: actionGames(1),
          online: true,
          controller: controller,
          onOpenGame: (_) async {},
          onOpenSchedule: () {},
        ),
      ),
    ));
    await tester.pump();
    expect(find.byKey(const ValueKey('action-home-loading')), findsOneWidget);
    gate.complete();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('action-home-resolved')), findsOneWidget);
  });

  test('member action distinguishes empty resolved partial and error states',
      () async {
    final empty = MemberActionController(
      (id) async => AttendanceSnapshot(id, null, const []),
      clock: () => DateTime.utc(2026, 8, 23),
    );
    await empty.load(principalScope: 'A', games: const [], online: true);
    expect(empty.state, MemberActionState.empty);

    final resolved = MemberActionController(
      (id) async => AttendanceSnapshot(id, AttendanceReply.attending, const []),
      clock: () => DateTime.utc(2026, 8, 23),
    );
    await resolved.load(
      principalScope: 'A',
      games: actionGames(1),
      online: true,
    );
    expect(resolved.state, MemberActionState.resolved);

    final failed = MemberActionController(
      (id) async => throw const NetworkException(),
      clock: () => DateTime.utc(2026, 8, 23),
    );
    await failed.load(
      principalScope: 'A',
      games: actionGames(1),
      online: true,
    );
    expect(failed.state, MemberActionState.retryableError);
  });
}
