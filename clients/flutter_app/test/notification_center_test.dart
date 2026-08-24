import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/app_theme.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/notification_center.dart';

const principal = Person('person_23', 'Member', [
  'games:read',
  'notifications:read',
]);
final now = DateTime.utc(2026, 8, 22, 12);

Map<String, dynamic> notificationJson({
  String id = 'notification_3',
  String? readAt,
  String createdAt = '2026-08-22T11:00:00Z',
  String visibleUntil = '2026-11-20T11:00:00Z',
}) =>
    {
      'id': id,
      'type': 'game_change',
      'title': '場地異動',
      'body': '比賽改到第二球場。',
      'created_at': createdAt,
      'visible_until': visibleUntil,
      'read_at': readAt,
    };

MobileNotification makeNotification({
  String id = 'notification_3',
  String? readAt,
  String createdAt = '2026-08-22T11:00:00Z',
  String visibleUntil = '2026-11-20T11:00:00Z',
}) =>
    MobileNotification.fromJson(notificationJson(
      id: id,
      readAt: readAt,
      createdAt: createdAt,
      visibleUntil: visibleUntil,
    ));

class FakeNotificationClient implements NotificationClient {
  List<MobileNotification> values = [makeNotification()];
  Object? failure;
  int calls = 0;

  void _check() {
    calls++;
    if (failure != null) throw failure!;
  }

  @override
  Future<MobileNotification> notification(String id) async {
    _check();
    return values.singleWhere((item) => item.id == id);
  }

  @override
  Future<List<MobileNotification>> notifications({
    bool unreadOnly = false,
  }) async {
    _check();
    return values;
  }

  @override
  Future<int> unreadCount() async {
    _check();
    return values.where((item) => !item.isRead).length;
  }

  @override
  Future<NotificationReadResult> markRead(String id) async {
    _check();
    final result = NotificationReadResult(id, now, true);
    values = [for (final item in values) item.markRead(now)];
    return result;
  }

  @override
  Future<NotificationReadAllResult> markAllRead() async {
    _check();
    values = [for (final item in values) item.markRead(now)];
    return const NotificationReadAllResult(1, 0);
  }
}

class DelayedNotificationClient extends FakeNotificationClient {
  final loads = <Completer<List<MobileNotification>>>[];
  final filters = <bool>[];

  @override
  Future<List<MobileNotification>> notifications({bool unreadOnly = false}) {
    filters.add(unreadOnly);
    final load = Completer<List<MobileNotification>>();
    loads.add(load);
    return load.future;
  }
}

class ScriptedPagedClient extends FakeNotificationClient
    implements PagedNotificationClient {
  final pages = <Completer<NotificationPage>>[];
  final filters = <bool>[];

  @override
  Future<NotificationPage> page({String? cursor, bool unreadOnly = false}) {
    filters.add(unreadOnly);
    final result = Completer<NotificationPage>();
    pages.add(result);
    return result.future;
  }
}

class ScriptedTransport implements ApiTransport {
  final responses = <ApiResponse>[];
  final calls =
      <(String, String, Map<String, String>, Map<String, dynamic>?)>[];

  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    calls.add((method, path, headers, body));
    return responses.removeAt(0);
  }
}

void main() {
  test('notification wire model requires exactly 90 days', () {
    expect(makeNotification().type, MobileNotificationType.gameChange);
    expect(
      () => MobileNotification.fromJson({
        ...notificationJson(),
        'body': List.filled(501, 'x').join(),
      }),
      throwsA(isA<ContractException>()),
    );
    expect(
      () => MobileNotification.fromJson({
        ...notificationJson(),
        'type': 'unknown',
      }),
      throwsA(isA<ContractException>()),
    );
    expect(
      () => MobileNotification.fromJson({
        ...notificationJson(),
        'visible_until': '2026-11-20T10:59:59Z',
      }),
      throwsA(isA<ContractException>()),
    );
    for (final id in [
      'notification_9223372036854775808',
      'notification_1111111111111111111111111111111111111111',
    ]) {
      expect(
        () => MobileNotification.fromJson({...notificationJson(), 'id': id}),
        throwsA(isA<ContractException>()),
      );
    }
  });

  test('offline unread count is recomputed from still-visible cached rows',
      () async {
    final store = MemoryStore();
    final cache = NotificationCache(store, 'install');
    final expiring = makeNotification(
      id: 'notification_2',
      createdAt: '2026-05-24T11:00:00Z',
      visibleUntil: '2026-08-22T11:00:00Z',
    );
    final retained = makeNotification(
      createdAt: '2026-05-25T11:00:00Z',
      visibleUntil: '2026-08-23T11:00:00Z',
    );
    await cache.save(
      principal,
      [retained, expiring],
      DateTime.utc(2026, 8, 22, 10),
      unreadCount: 2,
    );

    final loaded = await cache.loadFor(
      principal,
      now,
      sessionPresent: true,
    );
    expect(loaded!.items.map((item) => item.id), ['notification_3']);
    expect(loaded.unreadCount, 1);
  });

  test(
    'cache is principal scoped and purges identity, capability, and corruption',
    () async {
      final store = MemoryStore();
      final cache = NotificationCache(store, 'install');
      await cache.save(principal, [makeNotification()], now);
      expect(
        (await cache.loadFor(
          principal,
          now,
          sessionPresent: true,
        ))!
            .unreadCount,
        1,
      );

      const other = Person('person_99', 'Other', ['notifications:read']);
      expect(await cache.loadFor(other, now, sessionPresent: true), isNull);
      expect(store.values, isEmpty);

      await cache.save(principal, [makeNotification()], now);
      const withoutCapability = Person('person_23', 'Member', ['games:read']);
      expect(
        await cache.loadFor(withoutCapability, now, sessionPresent: true),
        isNull,
      );
      expect(store.values, isEmpty);

      await cache.save(principal, [makeNotification()], now);
      store.values['notification-cache:v1:install:person_23'] = '{corrupt';
      expect(await cache.loadFor(principal, now, sessionPresent: true), isNull);
      expect(store.values, isEmpty);
    },
  );

  test('fresh person change purges the prior notification partition', () async {
    final store = MemoryStore();
    final cache = NotificationCache(store, 'install');
    await cache.save(principal, [makeNotification()], now);

    const next = Person('person_99', 'Other', ['notifications:read']);
    await cache.reconcileFreshPrincipal(principal, next);

    expect(store.values, isEmpty);
  });

  test('stale A capability reconciliation cannot clear indexed B cache',
      () async {
    final store = MemoryStore();
    final cache = NotificationCache(store, 'install');
    const b = Person('person_99', 'B', ['notifications:read']);
    await cache.save(b, [makeNotification()], now);

    await cache.reconcileFreshPrincipal(
      const Person('person_23', 'A', ['notifications:read']),
      const Person('person_23', 'A', ['games:read']),
    );

    expect((await cache.loadFor(b, now, sessionPresent: true))?.personId,
        'person_99');
  });

  test(
    'offline centre is read-only and makes zero notification calls',
    () async {
      final client = FakeNotificationClient();
      final cache = NotificationCache(MemoryStore(), 'install');
      await cache.save(principal, [makeNotification()], now);
      final controller = NotificationCenterController(
        client: client,
        cache: cache,
        principal: principal,
        clock: () => now,
      );

      await controller.load(online: false);
      expect(controller.state, NotificationCenterState.offline);
      expect(client.calls, 0);
      expect(
        controller.markRead('notification_3', online: false),
        throwsA(isA<OfflineReadOnlyException>()),
      );
      expect(
        controller.markAllRead(online: false),
        throwsA(isA<OfflineReadOnlyException>()),
      );
      expect(client.calls, 0);
    },
  );

  test('rapid notification loads share one in-flight request', () async {
    final client = DelayedNotificationClient();
    final controller = NotificationCenterController(
      client: client,
      cache: NotificationCache(MemoryStore(), 'install'),
      principal: principal,
      clock: () => now,
    );

    final first = controller.load(online: true);
    final second = controller.load(online: true);
    expect(client.loads, hasLength(1));
    client.loads.single.complete([makeNotification()]);
    await Future.wait([first, second]);

    expect(controller.unreadCount, 1);
    expect(controller.state, NotificationCenterState.online);
  });

  test('invalidation prevents a pending load from restoring notification state',
      () async {
    final client = DelayedNotificationClient();
    final controller = NotificationCenterController(
      client: client,
      cache: NotificationCache(MemoryStore(), 'install'),
      principal: principal,
      clock: () => now,
    );
    final pending = controller.load(online: true);
    controller.invalidate();
    client.loads.single.complete([makeNotification()]);
    await pending;
    expect(controller.state, NotificationCenterState.unauthorized);
    expect(controller.items, isEmpty);
  });

  test('filter change invalidates an older in-flight list result', () async {
    final client = DelayedNotificationClient();
    final controller = NotificationCenterController(
      client: client,
      cache: NotificationCache(MemoryStore(), 'install'),
      principal: principal,
      clock: () => now,
    );
    final all = controller.load(online: true);
    final unread = controller.setUnreadOnly(true, online: true);
    expect(client.filters, [false, true]);
    client.loads[1].complete([makeNotification(id: 'notification_2')]);
    await unread;
    client.loads[0].complete([makeNotification(id: 'notification_3')]);
    await all;
    expect(controller.items.single.id, 'notification_2');
    expect(controller.unreadOnly, isTrue);
  });

  test('unread presentation and pagination never replace canonical all cache',
      () async {
    final store = MemoryStore();
    final cache = NotificationCache(store, 'install');
    final client = ScriptedPagedClient();
    final controller = NotificationCenterController(
      client: client,
      cache: cache,
      principal: principal,
      clock: () => now,
    );
    final read = makeNotification(
      id: 'notification_1',
      readAt: '2026-08-22T11:30:00Z',
    );
    final unread = makeNotification(id: 'notification_2');
    final all = controller.load(online: true);
    client.pages[0].complete(NotificationPage([read, unread], null));
    await all;
    final filtered = controller.setUnreadOnly(true, online: true);
    client.pages[1].complete(NotificationPage([unread], 'more'));
    await filtered;
    final more = controller.loadMore(online: true);
    client.pages[2].complete(const NotificationPage([], null));
    await more;

    final offlineAll = NotificationCenterController(
      client: FakeNotificationClient(),
      cache: cache,
      principal: principal,
      clock: () => now,
    );
    await offlineAll.load(online: false);
    expect(offlineAll.items.map((item) => item.id),
        ['notification_1', 'notification_2']);
    final offlineUnread = NotificationCenterController(
      client: FakeNotificationClient(),
      cache: cache,
      principal: principal,
      clock: () => now,
    );
    await offlineUnread.setUnreadOnly(true, online: false);
    expect(offlineUnread.items.map((item) => item.id), ['notification_2']);
  });

  test('stale generic failure cannot overwrite newer filter success', () async {
    final cache = NotificationCache(MemoryStore(), 'install');
    final client = ScriptedPagedClient();
    final controller = NotificationCenterController(
      client: client,
      cache: cache,
      principal: principal,
      clock: () => now,
    );
    final all = controller.load(online: true);
    final unread = controller.setUnreadOnly(true, online: true);
    client.pages[1].complete(
      NotificationPage([makeNotification(id: 'notification_2')], null),
    );
    await unread;
    client.pages[0].completeError(StateError('old failure'));
    await all;
    expect(controller.unreadOnly, isTrue);
    expect(controller.state, NotificationCenterState.online);
    expect(controller.items.single.id, 'notification_2');
  });

  test('offline without valid cache is explicitly non-authoritative', () async {
    final controller = NotificationCenterController(
      client: FakeNotificationClient(),
      cache: NotificationCache(MemoryStore(), 'install'),
      principal: principal,
      clock: () => now,
    );
    await controller.load(online: false);
    expect(
        controller.state, NotificationCenterState.offlineEvidenceUnavailable);
    expect(controller.items, isEmpty);
  });

  test('terminal list failures invalidate and notify root exactly once',
      () async {
    for (final failure in <Object>[
      const SessionExpiredException(),
      const ApiError(ApiErrorCode.unauthenticated, false, null),
    ]) {
      final store = MemoryStore();
      final cache = NotificationCache(store, 'install');
      await cache.save(principal, [makeNotification()], now);
      var terminalCalls = 0;
      final controller = NotificationCenterController(
        client: FakeNotificationClient()..failure = failure,
        cache: cache,
        principal: principal,
        clock: () => now,
        onTerminalSession: () => terminalCalls++,
      );

      await controller.load(online: true);
      expect(terminalCalls, 1);
      expect(controller.state, NotificationCenterState.unauthorized);
      expect(controller.items, isEmpty);
      expect(store.values, isEmpty);
    }
  });

  test(
      'forbidden list failure clears notification state without ending session',
      () async {
    final store = MemoryStore();
    final cache = NotificationCache(store, 'install');
    await cache.save(principal, [makeNotification()], now);
    var terminalCalls = 0;
    final controller = NotificationCenterController(
      client: FakeNotificationClient()
        ..failure = const ApiError(ApiErrorCode.forbidden, false, null),
      cache: cache,
      principal: principal,
      clock: () => now,
      onTerminalSession: () => terminalCalls++,
    );

    await controller.load(online: true);
    expect(terminalCalls, 0);
    expect(controller.state, NotificationCenterState.unauthorized);
    expect(store.values, isEmpty);
  });

  test(
    'authorization loss and terminal session clear purge notification cache',
    () async {
      final store = MemoryStore();
      final cache = NotificationCache(store, 'install');
      await cache.save(principal, [makeNotification()], now);
      final client = FakeNotificationClient()
        ..failure = const ApiError(ApiErrorCode.forbidden, false, null);
      final controller = NotificationCenterController(
        client: client,
        cache: cache,
        principal: principal,
        clock: () => now,
      );
      await controller.load(online: true);
      expect(controller.state, NotificationCenterState.unauthorized);
      expect(store.values, isEmpty);

      await cache.save(principal, [makeNotification()], now);
      final sessions = SessionController(
        ScriptedTransport(),
        store,
        'install',
        SecureIds(),
        terminalPurge: cache.clear,
      );
      await sessions.accept(
        const SessionEnvelope(
          accessToken: 'access',
          refreshToken: 'refresh-token-with-more-than-32-characters',
          sessionId: 'session',
          expiresIn: 900,
        ),
      );
      await sessions.clear();
      expect(store.values, isEmpty);
    },
  );

  test('terminal authorized 401 purges notification cache and session',
      () async {
    final store = MemoryStore();
    final cache = NotificationCache(store, 'install');
    await cache.save(principal, [makeNotification()], now);
    final transport = ScriptedTransport()
      ..responses.addAll([
        const ApiResponse(401, null),
        const ApiResponse(401, null),
      ]);
    final sessions = SessionController(
      transport,
      store,
      'install',
      SecureIds(),
      terminalPurge: cache.clear,
    );
    await sessions.accept(
      const SessionEnvelope(
        accessToken: 'access',
        refreshToken: 'refresh-token-with-more-than-32-characters',
        sessionId: 'session',
        expiresIn: 900,
      ),
    );

    await expectLater(
      sessions.authorized('GET', '/me'),
      throwsA(isA<SessionExpiredException>()),
    );
    expect(store.values, isEmpty);
  });

  test(
    'transport paginates deterministically and sends empty idempotent puts',
    () async {
      final transport = ScriptedTransport()
        ..responses.addAll([
          ApiResponse(200, {
            'items': [notificationJson()],
            'next_cursor': 'next',
          }),
          ApiResponse(200, {
            'items': [notificationJson(id: 'notification_2')],
            'next_cursor': null,
          }),
          const ApiResponse(200, {'unread_count': 2}),
          ApiResponse(200, {
            'notification_id': 'notification_3',
            'read_at': '2026-08-22T12:00:00Z',
            'changed': true,
          }),
          const ApiResponse(200, {'changed_count': 2, 'unread_count': 0}),
        ]);
      final sessions = SessionController(
        transport,
        MemoryStore(),
        'install',
        SecureIds(),
      );
      await sessions.accept(
        const SessionEnvelope(
          accessToken: 'access',
          refreshToken: 'refresh-token-with-more-than-32-characters',
          sessionId: 'session',
          expiresIn: 900,
        ),
      );
      final api = NotificationApi(sessions);

      expect(await api.notifications(), hasLength(2));
      expect(await api.unreadCount(), 2);
      expect((await api.markRead('notification_3')).changed, isTrue);
      expect((await api.markAllRead()).changedCount, 2);
      expect(transport.calls[1].$2, contains('cursor=next'));
      expect(transport.calls[3].$4, isEmpty);
      expect(transport.calls[4].$4, isEmpty);
    },
  );

  testWidgets('standalone centre renders offline state and disables writes', (
    tester,
  ) async {
    final cache = NotificationCache(MemoryStore(), 'install');
    await cache.save(principal, [makeNotification()], now);
    final controller = NotificationCenterController(
      client: FakeNotificationClient(),
      cache: cache,
      principal: principal,
      clock: () => now,
    );
    await controller.load(online: false);

    await tester.pumpWidget(
      MaterialApp(
        home: NotificationCenter(controller: controller, online: false),
      ),
    );
    expect(find.text('通知中心 (1)'), findsOneWidget);
    expect(find.textContaining('離線模式'), findsOneWidget);
    expect(find.text('場地異動'), findsOneWidget);
    expect(
      tester
          .widget<TextButton>(find.widgetWithText(TextButton, '全部已讀'))
          .onPressed,
      isNull,
    );
  });

  testWidgets(
      'centre gives unread rows, sync state, and read rows distinct hierarchy',
      (tester) async {
    final controller = NotificationCenterController(
      client: FakeNotificationClient()
        ..values = [
          makeNotification(),
          makeNotification(
            id: 'notification_4',
            readAt: '2026-08-22T11:30:00Z',
          ),
        ],
      cache: NotificationCache(MemoryStore(), 'install'),
      principal: principal,
      clock: () => now,
    );
    await controller.load(online: true);

    await tester.pumpWidget(
      MaterialApp(
        theme: appTheme(Brightness.light),
        home: NotificationCenter(controller: controller, online: true),
      ),
    );

    expect(find.text('2 則通知'), findsOneWidget);
    expect(find.text('1 則未讀'), findsOneWidget);
    expect(find.text('未讀'), findsAtLeastNWidgets(2));
    expect(find.text('已讀'), findsOneWidget);
    expect(find.textContaining('已同步'), findsOneWidget);
  });

  testWidgets('detail presents delivery and read metadata as status badges',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: appTheme(Brightness.light),
        home: NotificationDetailPage(
          notification: makeNotification(readAt: '2026-08-22T11:30:00Z'),
        ),
      ),
    );

    expect(find.text('通知詳情'), findsOneWidget);
    expect(find.text('已讀'), findsOneWidget);
    expect(find.textContaining('送達於'), findsOneWidget);
    expect(find.textContaining('已讀於'), findsOneWidget);
  });

  testWidgets(
      'constrained large-text app bar keeps back, title, and actions reachable',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final controller = NotificationCenterController(
      client: FakeNotificationClient(),
      cache: NotificationCache(MemoryStore(), 'install'),
      principal: principal,
      clock: () => now,
    );
    await controller.load(online: true);

    await tester.pumpWidget(
      MaterialApp(
        theme: appTheme(Brightness.light),
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: const TextScaler.linear(1.3),
          ),
          child: child!,
        ),
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => NotificationCenter(
                    controller: controller,
                    online: true,
                  ),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(find.byType(BackButton), findsOneWidget);
    expect(find.text('通知中心'), findsOneWidget);
    expect(find.byKey(const ValueKey('notification-refresh')), findsOneWidget);
    expect(find.byTooltip('更多通知操作'), findsOneWidget);

    await tester.tap(find.byTooltip('更多通知操作'));
    await tester.pumpAndSettle();
    expect(find.text('全部已讀'), findsOneWidget);
    await tester.tapAt(const Offset(12, 300));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    expect(find.text('open'), findsOneWidget);
  });
}
