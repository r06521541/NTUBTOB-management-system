import 'package:flutter/material.dart';

import 'integration.dart';

enum NotificationCenterState {
  initial,
  loading,
  online,
  offline,
  empty,
  unauthorized,
  error,
}

class NotificationCenterController extends ChangeNotifier {
  NotificationCenterController({
    required this.client,
    required this.cache,
    required this.principal,
    DateTime Function()? clock,
  }) : clock = clock ?? DateTime.now;

  final NotificationClient client;
  final NotificationCache cache;
  final Person principal;
  final DateTime Function() clock;
  NotificationCenterState state = NotificationCenterState.initial;
  List<MobileNotification> items = const [];
  DateTime? lastSyncedAt;
  int unreadCount = 0;
  Future<void>? _loadOperation;
  Future<void>? _mutationOperation;
  bool get readOnly => state == NotificationCenterState.offline;
  bool get busy => _loadOperation != null || _mutationOperation != null;

  Future<void> load({required bool online, bool sessionPresent = true}) {
    final existing = _loadOperation;
    if (existing != null) return existing;
    late final Future<void> operation;
    operation = _loadOnce(online: online, sessionPresent: sessionPresent)
        .whenComplete(() {
      if (identical(_loadOperation, operation)) {
        _loadOperation = null;
        notifyListeners();
      }
    });
    _loadOperation = operation;
    return operation;
  }

  Future<void> _loadOnce({
    required bool online,
    required bool sessionPresent,
  }) async {
    state = NotificationCenterState.loading;
    notifyListeners();
    if (!sessionPresent || !principal.canReadNotifications) {
      await cache.clear();
      _set(NotificationCenterState.unauthorized, const [], null);
      return;
    }
    if (!online) {
      await _loadCache();
      return;
    }
    try {
      final fresh = await client.notifications();
      final serverUnreadCount = await client.unreadCount();
      final now = clock().toUtc();
      await cache.save(principal, fresh, now, unreadCount: serverUnreadCount);
      items = List.unmodifiable(fresh);
      unreadCount = serverUnreadCount;
      lastSyncedAt = now;
      state = fresh.isEmpty
          ? NotificationCenterState.empty
          : NotificationCenterState.online;
      notifyListeners();
    } on AuthorizedRequestNetworkException {
      await _loadCache();
    } on SessionExpiredException {
      await cache.clear();
      _set(NotificationCenterState.unauthorized, const [], null);
    } on ApiError catch (error) {
      if (error.code == ApiErrorCode.forbidden ||
          error.code == ApiErrorCode.unauthenticated ||
          error.code == ApiErrorCode.sessionExpired) {
        await cache.clear();
        _set(NotificationCenterState.unauthorized, const [], null);
      } else {
        state = NotificationCenterState.error;
        notifyListeners();
      }
    } on Object {
      state = NotificationCenterState.error;
      notifyListeners();
    }
  }

  Future<void> _loadCache() async {
    final cached = await cache.loadFor(
      principal,
      clock().toUtc(),
      sessionPresent: true,
    );
    if (cached == null) {
      _set(NotificationCenterState.empty, const [], null);
      return;
    }
    items = List.unmodifiable(cached.items);
    unreadCount = cached.unreadCount;
    lastSyncedAt = cached.lastSyncedAt;
    state = NotificationCenterState.offline;
    notifyListeners();
  }

  Future<MobileNotification> detail(String id, {required bool online}) async {
    MobileNotification? cached;
    for (final item in items) {
      if (item.id == id) {
        cached = item;
        break;
      }
    }
    if (!online) {
      if (cached == null) throw const OfflineReadOnlyException();
      return cached;
    }
    return client.notification(id);
  }

  Future<void> markRead(String id, {required bool online}) async {
    if (!online) throw const OfflineReadOnlyException();
    final existing = _mutationOperation;
    if (existing != null) return existing;
    late final Future<void> operation;
    operation = _markReadOnce(id).whenComplete(() {
      if (identical(_mutationOperation, operation)) {
        _mutationOperation = null;
        notifyListeners();
      }
    });
    _mutationOperation = operation;
    notifyListeners();
    return operation;
  }

  Future<void> _markReadOnce(String id) async {
    final result = await client.markRead(id);
    items = List.unmodifiable([
      for (final item in items)
        if (item.id == id) item.markRead(result.readAt) else item,
    ]);
    if (result.changed && unreadCount > 0) unreadCount--;
    await cache.save(principal, items, lastSyncedAt ?? clock(),
        unreadCount: unreadCount);
    state = items.isEmpty
        ? NotificationCenterState.empty
        : NotificationCenterState.online;
    notifyListeners();
  }

  Future<void> markAllRead({required bool online}) async {
    if (!online) throw const OfflineReadOnlyException();
    final existing = _mutationOperation;
    if (existing != null) return existing;
    late final Future<void> operation;
    operation = _markAllReadOnce().whenComplete(() {
      if (identical(_mutationOperation, operation)) {
        _mutationOperation = null;
        notifyListeners();
      }
    });
    _mutationOperation = operation;
    notifyListeners();
    return operation;
  }

  Future<void> _markAllReadOnce() async {
    final result = await client.markAllRead();
    final readAt = clock().toUtc();
    items = List.unmodifiable(
      items.map((item) => item.markRead(readAt)).toList(growable: false),
    );
    unreadCount = result.unreadCount;
    await cache.save(principal, items, lastSyncedAt ?? readAt,
        unreadCount: unreadCount);
    state = items.isEmpty
        ? NotificationCenterState.empty
        : NotificationCenterState.online;
    notifyListeners();
  }

  void _set(
    NotificationCenterState next,
    List<MobileNotification> nextItems,
    DateTime? syncedAt,
  ) {
    state = next;
    items = nextItems;
    unreadCount = nextItems.where((item) => !item.isRead).length;
    lastSyncedAt = syncedAt;
    notifyListeners();
  }
}

class NotificationCenter extends StatelessWidget {
  const NotificationCenter({
    super.key,
    required this.controller,
    required this.online,
    this.onOpen,
  });

  final NotificationCenterController controller;
  final bool online;
  final ValueChanged<MobileNotification>? onOpen;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) => Scaffold(
          appBar: AppBar(
            title: Text('通知中心 (${controller.unreadCount})'),
            actions: [
              IconButton(
                key: const ValueKey('notification-refresh'),
                tooltip: '重新整理通知',
                onPressed: controller.busy
                    ? null
                    : () => controller.load(online: online),
                icon: const Icon(Icons.refresh),
              ),
              TextButton(
                onPressed:
                    online && controller.unreadCount > 0 && !controller.busy
                        ? () => controller.markAllRead(online: true)
                        : null,
                child: const Text('全部已讀'),
              ),
            ],
          ),
          body: _body(context),
        ),
      );

  Widget _body(BuildContext context) {
    if (controller.state == NotificationCenterState.loading ||
        controller.state == NotificationCenterState.initial) {
      return const Center(child: CircularProgressIndicator());
    }
    if (controller.state == NotificationCenterState.unauthorized) {
      return const Center(child: Text('目前無法查看通知，請重新登入。'));
    }
    if (controller.state == NotificationCenterState.error) {
      return const Center(child: Text('通知載入失敗，請稍後再試。'));
    }
    if (controller.items.isEmpty) {
      return const Center(child: Text('目前沒有通知'));
    }
    return Column(
      children: [
        if (controller.readOnly)
          const MaterialBanner(
            content: Text('離線模式：顯示上次同步內容，無法變更已讀狀態。'),
            actions: [SizedBox.shrink()],
          ),
        Expanded(
          child: ListView.builder(
            itemCount: controller.items.length,
            itemBuilder: (context, index) {
              final item = controller.items[index];
              return ListTile(
                leading: Icon(
                  item.isRead
                      ? Icons.notifications_none
                      : Icons.notifications_active,
                ),
                title: Text(item.title),
                subtitle: Text(item.body),
                selected: !item.isRead,
                onTap: controller.busy
                    ? null
                    : () {
                        onOpen?.call(item);
                        if (online && !item.isRead) {
                          controller.markRead(item.id, online: true);
                        }
                      },
              );
            },
          ),
        ),
      ],
    );
  }
}
