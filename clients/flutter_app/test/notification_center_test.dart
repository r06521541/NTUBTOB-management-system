import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
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
}
