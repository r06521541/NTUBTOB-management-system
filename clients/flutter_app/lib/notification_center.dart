import 'package:flutter/material.dart';

import 'app_theme.dart';

import 'integration.dart';

enum NotificationCenterState {
  initial,
  loading,
  online,
  offline,
  offlineEvidenceUnavailable,
  empty,
  unauthorized,
  error,
}

class NotificationCenterController extends ChangeNotifier {
  NotificationCenterController({
    required this.client,
    required this.cache,
    required this.principal,
    this.onTerminalSession,
    DateTime Function()? clock,
  }) : clock = clock ?? DateTime.now;

  final NotificationClient client;
  final NotificationCache cache;
  final Person principal;
  final DateTime Function() clock;
  final VoidCallback? onTerminalSession;
  NotificationCenterState state = NotificationCenterState.initial;
  List<MobileNotification> items = const [];
  DateTime? lastSyncedAt;
  int unreadCount = 0;
  String? nextCursor;
  bool unreadOnly = false;
  List<MobileNotification> _canonicalItems = const [];
  bool _canonicalComplete = false;
  Future<void>? _loadOperation;
  Future<void>? _mutationOperation;
  Future<void> _cacheTail = Future.value();
  int _epoch = 0;
  bool get readOnly => state == NotificationCenterState.offline;
  bool get busy => _loadOperation != null || _mutationOperation != null;

  Future<void> invalidate() {
    _epoch++;
    _loadOperation = null;
    _mutationOperation = null;
    _set(NotificationCenterState.unauthorized, const [], null);
    return _enqueueCache(cache.clear);
  }

  Future<void> _enqueueCache(Future<void> Function() operation) {
    _cacheTail = _cacheTail.catchError((_) {}).then((_) => operation());
    return _cacheTail;
  }

  Future<void> _saveIfCurrent(
    int epoch,
    List<MobileNotification> nextItems,
    DateTime syncedAt, {
    required int nextUnreadCount,
  }) async {
    await _enqueueCache(() async {
      if (epoch != _epoch) {
        return;
      }
      await cache.save(
        principal,
        nextItems,
        syncedAt,
        unreadCount: nextUnreadCount,
      );
    });
  }

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
    final epoch = _epoch;
    state = NotificationCenterState.loading;
    notifyListeners();
    if (!sessionPresent || !principal.canReadNotifications) {
      await invalidate();
      if (epoch != _epoch) return;
      _set(NotificationCenterState.unauthorized, const [], null);
      return;
    }
    if (!online) {
      await _loadCache();
      return;
    }
    try {
      final pageClient = client is PagedNotificationClient
          ? client as PagedNotificationClient
          : null;
      final page = pageClient == null
          ? null
          : await pageClient.page(unreadOnly: unreadOnly);
      final fresh =
          page?.items ?? await client.notifications(unreadOnly: unreadOnly);
      final serverUnreadCount = await client.unreadCount();
      if (epoch != _epoch) return;
      final now = clock().toUtc();
      if (!unreadOnly && page?.nextCursor == null) {
        _canonicalItems = List.unmodifiable(fresh);
        _canonicalComplete = true;
        await _saveIfCurrent(epoch, _canonicalItems, now,
            nextUnreadCount: serverUnreadCount);
      }
      if (epoch != _epoch) return;
      items = List.unmodifiable(fresh);
      nextCursor = page?.nextCursor;
      unreadCount = serverUnreadCount;
      lastSyncedAt = now;
      state = fresh.isEmpty
          ? NotificationCenterState.empty
          : NotificationCenterState.online;
      notifyListeners();
    } on AuthorizedRequestNetworkException {
      if (epoch == _epoch) await _loadCache(epoch: epoch);
    } on SessionExpiredException {
      await invalidate();
      onTerminalSession?.call();
    } on ApiError catch (error) {
      if (error.code == ApiErrorCode.forbidden) {
        await invalidate();
      } else if (error.code == ApiErrorCode.unauthenticated ||
          error.code == ApiErrorCode.sessionExpired) {
        await invalidate();
        onTerminalSession?.call();
      } else {
        if (epoch == _epoch) {
          state = NotificationCenterState.error;
          notifyListeners();
        }
      }
    } on Object {
      if (epoch == _epoch) {
        state = NotificationCenterState.error;
        notifyListeners();
      }
    }
  }

  Future<void> setUnreadOnly(bool value, {required bool online}) async {
    if (unreadOnly == value) return;
    _epoch++;
    _loadOperation = null;
    unreadOnly = value;
    nextCursor = null;
    await load(online: online);
  }

  Future<void> loadMore({required bool online}) async {
    if (!online ||
        nextCursor == null ||
        busy ||
        client is! PagedNotificationClient) {
      return;
    }
    final epoch = _epoch;
    final cursor = nextCursor;
    late final Future<void> operation;
    operation = _loadMoreOnce(epoch, cursor!).whenComplete(() {
      if (identical(_loadOperation, operation)) {
        _loadOperation = null;
        notifyListeners();
      }
    });
    _loadOperation = operation;
    await _loadOperation;
  }

  Future<void> _loadMoreOnce(int epoch, String cursor) async {
    try {
      final page = await (client as PagedNotificationClient)
          .page(cursor: cursor, unreadOnly: unreadOnly);
      if (epoch != _epoch) return;
      final ids = items.map((item) => item.id).toSet();
      if (page.items.any((item) => !ids.add(item.id))) {
        throw const ContractException('duplicate notification page item');
      }
      items = List.unmodifiable([...items, ...page.items]);
      nextCursor = page.nextCursor;
      if (!unreadOnly && nextCursor == null) {
        _canonicalItems = items;
        _canonicalComplete = true;
        await _saveIfCurrent(
          epoch,
          _canonicalItems,
          lastSyncedAt ?? clock().toUtc(),
          nextUnreadCount: unreadCount,
        );
      }
      if (epoch == _epoch) notifyListeners();
    } on SessionExpiredException {
      await invalidate();
      onTerminalSession?.call();
    } on ApiError catch (error) {
      if (error.code == ApiErrorCode.unauthenticated ||
          error.code == ApiErrorCode.sessionExpired) {
        await invalidate();
        onTerminalSession?.call();
      } else if (error.code == ApiErrorCode.forbidden) {
        await invalidate();
      } else {
        rethrow;
      }
    }
  }

  Future<void> _loadCache({int? epoch}) async {
    final operationEpoch = epoch ?? _epoch;
    final cached = await cache.loadFor(
      principal,
      clock().toUtc(),
      sessionPresent: true,
    );
    if (operationEpoch != _epoch) return;
    if (cached == null) {
      _set(NotificationCenterState.offlineEvidenceUnavailable, const [], null);
      return;
    }
    _canonicalItems = List.unmodifiable(cached.items);
    _canonicalComplete = true;
    items = unreadOnly
        ? List.unmodifiable(_canonicalItems.where((item) => !item.isRead))
        : _canonicalItems;
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
    final epoch = _epoch;
    final result = await _terminalAware(() => client.markRead(id));
    if (result == null) return;
    if (epoch != _epoch) return;
    items = List.unmodifiable([
      for (final item in items)
        if (item.id == id) item.markRead(result.readAt) else item,
    ]);
    _canonicalItems = List.unmodifiable([
      for (final item in _canonicalItems)
        if (item.id == id) item.markRead(result.readAt) else item,
    ]);
    if (result.changed && unreadCount > 0) unreadCount--;
    if (_canonicalComplete) {
      await _saveIfCurrent(epoch, _canonicalItems, lastSyncedAt ?? clock(),
          nextUnreadCount: unreadCount);
    }
    if (epoch != _epoch) return;
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
    final epoch = _epoch;
    final result = await _terminalAware(() => client.markAllRead());
    if (result == null) return;
    if (epoch != _epoch) return;
    final readAt = clock().toUtc();
    items = List.unmodifiable(
      items.map((item) => item.markRead(readAt)).toList(growable: false),
    );
    _canonicalItems = List.unmodifiable(
      _canonicalItems.map((item) => item.markRead(readAt)),
    );
    unreadCount = result.unreadCount;
    if (_canonicalComplete) {
      await _saveIfCurrent(epoch, _canonicalItems, lastSyncedAt ?? readAt,
          nextUnreadCount: unreadCount);
    }
    if (epoch != _epoch) return;
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

  Future<T?> _terminalAware<T>(Future<T> Function() operation) async {
    try {
      return await operation();
    } on SessionExpiredException {
      await invalidate();
      onTerminalSession?.call();
      return null;
    } on ApiError catch (error) {
      if (error.code == ApiErrorCode.unauthenticated ||
          error.code == ApiErrorCode.sessionExpired) {
        await invalidate();
        onTerminalSession?.call();
        return null;
      }
      rethrow;
    }
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
  Widget build(BuildContext context) {
    final compactActions = MediaQuery.sizeOf(context).width <= 430 &&
        MediaQuery.textScalerOf(context).scale(1) > 1.2;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final canMarkAll =
            online && controller.unreadCount > 0 && !controller.busy;
        return Scaffold(
          appBar: AppBar(
            automaticallyImplyLeading: false,
            leading: const BackButton(),
            title: Text(
              compactActions ? '通知中心' : '通知中心 (${controller.unreadCount})',
            ),
            actions: [
              IconButton(
                key: const ValueKey('notification-refresh'),
                tooltip: '重新整理通知',
                onPressed: controller.busy
                    ? null
                    : () => controller.load(online: online),
                icon: const Icon(Icons.refresh),
              ),
              if (compactActions)
                PopupMenuButton<String>(
                  tooltip: '更多通知操作',
                  onSelected: (_) => controller.markAllRead(online: true),
                  itemBuilder: (_) => [
                    PopupMenuItem<String>(
                      value: 'mark-all-read',
                      enabled: canMarkAll,
                      child: const Text('全部已讀'),
                    ),
                  ],
                )
              else
                TextButton(
                  onPressed: canMarkAll
                      ? () => controller.markAllRead(online: true)
                      : null,
                  child: const Text('全部已讀'),
                ),
            ],
          ),
          body: _body(context),
        );
      },
    );
  }

  Widget _body(BuildContext context) {
    if (controller.state == NotificationCenterState.loading ||
        controller.state == NotificationCenterState.initial) {
      return const Center(
        child: AppStatusPanel(
          icon: Icons.notifications_outlined,
          title: '正在整理通知',
          message: '正在取得最新通知內容。',
          loading: true,
        ),
      );
    }
    if (controller.state == NotificationCenterState.unauthorized) {
      return const Center(
        child: AppStatusPanel(
          icon: Icons.lock_outline,
          title: '目前無法查看通知',
          message: '請重新登入後再試。',
          tone: AppStatusTone.warning,
        ),
      );
    }
    if (controller.state == NotificationCenterState.error) {
      return const Center(
        child: AppStatusPanel(
          icon: Icons.error_outline,
          title: '通知載入失敗',
          message: '請稍後再試。',
          tone: AppStatusTone.danger,
          liveRegion: true,
        ),
      );
    }
    if (controller.state ==
        NotificationCenterState.offlineEvidenceUnavailable) {
      return const Center(
        child: AppStatusPanel(
          icon: Icons.cloud_off_outlined,
          title: '沒有離線通知',
          message: '離線時沒有可驗證的通知快取，無法顯示通知。',
          tone: AppStatusTone.warning,
        ),
      );
    }
    if (controller.items.isEmpty) {
      return const Center(
        child: AppStatusPanel(
          icon: Icons.notifications_none,
          title: '目前沒有通知',
          message: '新的球隊消息會顯示在這裡。',
        ),
      );
    }
    final tokens = context.appTokens;
    final unreadLabel =
        controller.unreadCount == 0 ? '全部已讀' : '${controller.unreadCount} 則未讀';
    final syncedLabel = controller.lastSyncedAt == null
        ? '尚未同步'
        : '已同步 ${_formatDateTime(context, controller.lastSyncedAt!)}';
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.regular,
            AppSpacing.compact,
            AppSpacing.regular,
            0,
          ),
          child: AppSurfaceCard(
            padding: const EdgeInsets.all(AppSpacing.regular),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: tokens.accent.withValues(alpha: .16),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    controller.unreadCount == 0
                        ? Icons.notifications_none
                        : Icons.notifications_active_outlined,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
                const SizedBox(width: AppSpacing.regular),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${controller.items.length} 則通知',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        syncedLabel,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                AppStatusBadge(
                  label: unreadLabel,
                  tone: controller.unreadCount == 0
                      ? AppStatusTone.success
                      : AppStatusTone.warning,
                ),
              ],
            ),
          ),
        ),
        if (online)
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.regular,
              vertical: AppSpacing.compact,
            ),
            child: Align(
              alignment: Alignment.centerLeft,
              child: SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: false, label: Text('全部')),
                  ButtonSegment(value: true, label: Text('未讀'))
                ],
                selected: {controller.unreadOnly},
                onSelectionChanged: controller.busy
                    ? null
                    : (value) =>
                        controller.setUnreadOnly(value.single, online: true),
              ),
            ),
          ),
        if (controller.readOnly)
          const MaterialBanner(
            content: Text('離線模式：顯示上次同步內容，無法變更已讀狀態。'),
            actions: [SizedBox.shrink()],
          ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.regular,
              AppSpacing.compact,
              AppSpacing.regular,
              AppSpacing.regular,
            ),
            itemCount: controller.items.length,
            itemBuilder: (context, index) {
              final item = controller.items[index];
              final status = item.isRead ? '已讀' : '未讀';
              return AppSurfaceCard(
                padding: EdgeInsets.zero,
                child: ListTile(
                  leading: Icon(
                    item.isRead
                        ? Icons.notifications_none
                        : Icons.notifications_active,
                  ),
                  title: Text(
                    item.title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  subtitle: Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(item.body,
                            maxLines: 2, overflow: TextOverflow.ellipsis),
                        const SizedBox(height: 6),
                        Text(
                          _formatDateTime(context, item.createdAt),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  trailing: AppStatusBadge(
                    label: status,
                    tone: item.isRead
                        ? AppStatusTone.neutral
                        : AppStatusTone.warning,
                  ),
                  selected: !item.isRead,
                  onTap: controller.busy
                      ? null
                      : () {
                          onOpen?.call(item);
                          if (online && !item.isRead) {
                            controller.markRead(item.id, online: true);
                          }
                        },
                ),
              );
            },
          ),
        ),
        if (online && controller.nextCursor != null)
          TextButton(
              onPressed: controller.busy
                  ? null
                  : () => controller.loadMore(online: true),
              child: const Text('載入更多')),
      ],
    );
  }
}

class NotificationDetailPage extends StatelessWidget {
  const NotificationDetailPage({super.key, required this.notification});

  final MobileNotification notification;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('通知詳情')),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.regular),
        children: [
          AppPageTitle(
            eyebrow: '球隊通知',
            title: notification.title,
            subtitle: '送達於 ${_formatDateTime(context, notification.createdAt)}',
          ),
          const SizedBox(height: AppSpacing.regular),
          Wrap(
            spacing: AppSpacing.compact,
            runSpacing: AppSpacing.compact,
            children: [
              AppStatusBadge(
                label: notification.isRead ? '已讀' : '未讀',
                tone: notification.isRead
                    ? AppStatusTone.success
                    : AppStatusTone.warning,
                icon: notification.isRead
                    ? Icons.check_circle_outline
                    : Icons.mark_email_unread_outlined,
              ),
              if (notification.readAt != null)
                AppStatusBadge(
                  label:
                      '已讀於 ${_formatDateTime(context, notification.readAt!)}',
                  tone: AppStatusTone.neutral,
                  icon: Icons.schedule_outlined,
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.regular),
          AppSurfaceCard(
            padding: const EdgeInsets.all(AppSpacing.regular),
            child: Text(
              notification.body,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
          ),
        ],
      ),
    );
  }
}

String _formatDateTime(BuildContext context, DateTime value) {
  final local = value.toLocal();
  final localizations = MaterialLocalizations.of(context);
  return '${localizations.formatFullDate(local)} '
      '${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(local))}';
}
