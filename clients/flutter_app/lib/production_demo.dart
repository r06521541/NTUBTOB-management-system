import 'dart:math';

import 'package:flutter/material.dart';

import 'app_theme.dart';
import 'basic_app.dart';
import 'foundation.dart';
import 'integration.dart';
import 'local_preferences.dart';
import 'officer_prereview.dart';
import 'notification_center.dart';
import 'pending_review.dart';

enum ProductionDemoPersona { basic, officer }

enum ProductionDemoConnectivity { online, offline }

enum ProductionDemoDataState { populated, empty, error }

class ProductionDemoProbe {
  int unexpectedTransportCalls = 0;
  int gameReads = 0;
  int attendanceReads = 0;
  int reportReads = 0;
  int replyMutations = 0;
}

class ProductionDemoApp extends DemoApp {
  const ProductionDemoApp({super.key, required super.flavor, this.probe});

  final ProductionDemoProbe? probe;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: '虛構產品展示・${flavor.displayLabel}',
        theme: appTheme(Brightness.light),
        darkTheme: appTheme(Brightness.dark),
        home: ProductionDemoShell(probe: probe),
      );
}

class ProductionDemoShell extends StatefulWidget {
  const ProductionDemoShell({super.key, this.probe});

  final ProductionDemoProbe? probe;

  @override
  State<ProductionDemoShell> createState() => _ProductionDemoShellState();
}

class _ProductionDemoShellState extends State<ProductionDemoShell> {
  static final _lastSyncedAt = DateTime.utc(2026, 8, 21, 8, 30);
  static final _games = <Game>[
    Game(
      'game_901',
      DateTime.utc(2026, 9, 12, 6, 30),
      120,
      '虛構大學棒球場',
      '虛構校友隊',
      '範例友隊',
    ),
    Game(
      'game_902',
      DateTime.utc(2026, 9, 19, 7),
      90,
      '虛構河濱球場',
      '虛構校友隊',
      '示意來賓隊',
    ),
    Game(
      'game_903',
      DateTime.utc(2026, 10, 3, 5, 30),
      120,
      null,
      '示意猛虎隊',
      '虛構校友隊',
    ),
    Game(
      'game_904',
      DateTime.utc(2026, 10, 3, 8),
      90,
      '虛構市立球場',
      '範例海豚隊',
      '虛構校友隊',
    ),
  ];
  static const _basicPerson = Person('fictional-basic', '虛構一般使用者', [
    'games:read',
    'attendance:reply:self',
    'notifications:read',
  ]);
  static const _officerPerson = Person(
      'fictional-officer',
      '虛構幹部',
      [
        'games:read',
        'attendance:reply:self',
        'attendance:report:read',
        'notifications:read',
      ],
      accessLevel: AccessLevel.officer);

  late final ProductionDemoProbe _probe;
  late final _ProductionDemoApi _api;
  late final _ProductionDemoReportCache _reportCache;
  late final NotificationCache _notificationCache;
  late final _ProductionDemoNotificationClient _notificationClient;
  late final LocalPreferences _preferences;
  final _notificationControllers = <String, NotificationCenterController>{};
  ProductionDemoPersona _persona = ProductionDemoPersona.basic;
  ProductionDemoConnectivity _connectivity = ProductionDemoConnectivity.online;
  ProductionDemoDataState _dataState = ProductionDemoDataState.populated;

  @override
  void initState() {
    super.initState();
    _probe = widget.probe ?? ProductionDemoProbe();
    _api = _ProductionDemoApi(_probe, _games);
    _reportCache = _ProductionDemoReportCache(_fictionalReportUiModel);
    _notificationCache = NotificationCache(MemoryStore(), 'fictional-demo');
    _notificationClient = _ProductionDemoNotificationClient();
    _preferences = LocalPreferences(MemoryStore(), 'fictional-demo');
    _seedNotifications();
  }

  Future<void> _seedNotifications() async {
    final notifications = _notificationClient.values;
    await _notificationCache.save(
      _basicPerson,
      notifications,
      _lastSyncedAt,
      unreadCount: notifications.where((item) => !item.isRead).length,
    );
    await _notificationCache.save(
      _officerPerson,
      notifications,
      _lastSyncedAt,
      unreadCount: notifications.where((item) => !item.isRead).length,
    );
  }

  NotificationCenterController _notificationController(Person person) =>
      _notificationControllers.putIfAbsent(
        person.id,
        () => NotificationCenterController(
          client: _notificationClient,
          cache: _notificationCache,
          principal: person,
          clock: () => _lastSyncedAt,
        ),
      );

  @override
  Widget build(BuildContext context) {
    final person =
        _persona == ProductionDemoPersona.basic ? _basicPerson : _officerPerson;
    final online = _connectivity == ProductionDemoConnectivity.online;
    final games =
        _dataState == ProductionDemoDataState.empty ? <Game>[] : _games;
    return Scaffold(
      appBar: AppBar(title: const Text('虛構產品展示')),
      body: Column(
        children: [
          Semantics(
            key: const ValueKey('production-demo-fictional-banner'),
            label: '虛構展示資料，不使用帳號、不連線',
            child: const MaterialBanner(
              content: Text('虛構展示資料・不使用帳號・不連線'),
              actions: [SizedBox.shrink()],
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                const Text('角色：'),
                ChoiceChip(
                  key: const ValueKey('demo-persona-basic'),
                  label: const Text('一般使用者'),
                  selected: _persona == ProductionDemoPersona.basic,
                  onSelected: (_) =>
                      setState(() => _persona = ProductionDemoPersona.basic),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-persona-officer'),
                  label: const Text('幹部'),
                  selected: _persona == ProductionDemoPersona.officer,
                  onSelected: (_) =>
                      setState(() => _persona = ProductionDemoPersona.officer),
                ),
                const SizedBox(width: 12),
                const Text('連線：'),
                ChoiceChip(
                  key: const ValueKey('demo-connectivity-online'),
                  label: const Text('線上'),
                  selected: _connectivity == ProductionDemoConnectivity.online,
                  onSelected: (_) => setState(
                    () => _connectivity = ProductionDemoConnectivity.online,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-connectivity-offline'),
                  label: const Text('離線'),
                  selected: _connectivity == ProductionDemoConnectivity.offline,
                  onSelected: (_) => setState(
                    () => _connectivity = ProductionDemoConnectivity.offline,
                  ),
                ),
                const SizedBox(width: 12),
                const Text('資料：'),
                ChoiceChip(
                  key: const ValueKey('demo-data-populated'),
                  label: const Text('有資料'),
                  selected: _dataState == ProductionDemoDataState.populated,
                  onSelected: (_) => setState(
                    () => _dataState = ProductionDemoDataState.populated,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-data-empty'),
                  label: const Text('空資料'),
                  selected: _dataState == ProductionDemoDataState.empty,
                  onSelected: (_) => setState(
                    () => _dataState = ProductionDemoDataState.empty,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-data-error'),
                  label: const Text('錯誤'),
                  selected: _dataState == ProductionDemoDataState.error,
                  onSelected: (_) => setState(
                    () => _dataState = ProductionDemoDataState.error,
                  ),
                ),
              ],
            ),
          ),
          Wrap(children: [
            TextButton(
              key: const ValueKey('demo-pending-review'),
              onPressed: () =>
                  Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => PendingReviewPage(
                    client: PendingReviewClient(_DemoReviewTransport(),
                        'fictional-review', SecureIds(Random(149)))),
              )),
              child: const Text('待審核情境'),
            ),
            TextButton(
              key: const ValueKey('demo-settings'),
              onPressed: () =>
                  Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => LocalPreferencesPage(
                  preferences: _preferences,
                  permissions: const NotificationPermissionActions(
                      UnsupportedNotificationPermissionPort()),
                  onThemeChanged: (_) {},
                ),
              )),
              child: const Text('設定情境'),
            ),
            TextButton(
              key: const ValueKey('demo-onboarding'),
              onPressed: () =>
                  Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (routeContext) => OnboardingPage(
                    onComplete: () async => Navigator.of(routeContext).pop()),
              )),
              child: const Text('新手引導情境'),
            ),
          ]),
          const Divider(height: 1),
          Expanded(
            child: _dataState == ProductionDemoDataState.error
                ? const AuthStatePanel(
                    key: ValueKey('production-demo-error'),
                    state: AuthViewState.recoverableError,
                  )
                : BasicGamesView(
                    key: ValueKey(
                      'production-demo-games-${_persona.name}-'
                      '${_connectivity.name}-${_dataState.name}',
                    ),
                    api: _api,
                    person: person,
                    games: games,
                    online: online,
                    lastSyncedAt: _lastSyncedAt,
                    principalProvenance: online
                        ? PrincipalProvenance.freshServer
                        : PrincipalProvenance.offlineCache,
                    reportCache: _reportCache,
                    notificationController: _notificationController(person),
                    onRefresh: () async => true,
                  ),
          ),
        ],
      ),
    );
  }
}

class _DemoReviewTransport implements ApiTransport {
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    return const ApiResponse(200, {
      'status': 'pending',
      'messages': [
        {
          'id': 'message_1',
          'sender': 'admin',
          'body': '請補充球隊屆別。',
          'created_at': '2026-08-22T01:00:00Z',
          'redacted': false
        }
      ]
    });
  }
}

class _RejectingProductionDemoTransport implements ApiTransport {
  _RejectingProductionDemoTransport(this.probe);

  final ProductionDemoProbe probe;

  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    probe.unexpectedTransportCalls++;
    throw StateError('production demo transport must remain unused');
  }
}

class _ProductionDemoNotificationClient
    implements NotificationClient, PagedNotificationClient {
  List<MobileNotification> values = [
    MobileNotification.fromJson({
      'id': 'notification_901',
      'type': 'game_reminder',
      'title': '虛構賽事提醒',
      'body': '這是展示用的未讀通知。',
      'created_at': '2026-08-21T08:30:00Z',
      'visible_until': '2026-11-19T08:30:00Z',
      'read_at': null,
      'destination': {
        'type': 'notification',
        'notification_id': 'notification_901',
      },
    }),
    MobileNotification.fromJson({
      'id': 'notification_902',
      'type': 'game_change',
      'title': '虛構場地異動',
      'body': '這是展示用的已讀通知。',
      'created_at': '2026-08-20T08:30:00Z',
      'visible_until': '2026-11-18T08:30:00Z',
      'read_at': '2026-08-20T09:00:00Z',
      'destination': {'type': 'game', 'game_id': 'game_901'},
    }),
  ];

  @override
  Future<MobileNotification> notification(String id) async =>
      values.firstWhere((item) => item.id == id);

  @override
  Future<List<MobileNotification>> notifications(
          {bool unreadOnly = false}) async =>
      unreadOnly ? values.where((item) => !item.isRead).toList() : values;

  @override
  Future<NotificationPage> page(
      {String? cursor, bool unreadOnly = false}) async {
    final filtered =
        unreadOnly ? values.where((item) => !item.isRead).toList() : values;
    final index = cursor == null ? 0 : 1;
    if (index >= filtered.length) return const NotificationPage([], null);
    return NotificationPage([filtered[index]],
        index + 1 < filtered.length ? 'fictional-next' : null);
  }

  @override
  Future<int> unreadCount() async =>
      values.where((item) => !item.isRead).length;

  @override
  Future<NotificationReadResult> markRead(String id) async {
    const readAt = '2026-08-21T08:30:00Z';
    values = [
      for (final item in values)
        if (item.id == id)
          item.markRead(DateTime.parse(readAt).toUtc())
        else
          item,
    ];
    return NotificationReadResult(id, DateTime.parse(readAt).toUtc(), true);
  }

  @override
  Future<NotificationReadAllResult> markAllRead() async {
    final readAt = DateTime.utc(2026, 8, 21, 8, 30);
    values = [for (final item in values) item.markRead(readAt)];
    return const NotificationReadAllResult(1, 0);
  }
}

class _ProductionDemoApi extends BasicApi {
  factory _ProductionDemoApi(ProductionDemoProbe probe, List<Game> games) {
    final store = MemoryStore();
    final ids = SecureIds(Random(144));
    final transport = _RejectingProductionDemoTransport(probe);
    return _ProductionDemoApi._(probe, games, store, ids, transport);
  }

  _ProductionDemoApi._(
    this.probe,
    this._games,
    MemoryStore store,
    SecureIds ids,
    ApiTransport transport,
  ) : super(
          SessionController(transport, store, 'fictional-demo', ids),
          store,
          'fictional-demo',
          ids,
        );

  final ProductionDemoProbe probe;
  final List<Game> _games;
  AttendanceReply _ownReply = AttendanceReply.attending;

  Game _findGame(String id) => _games.firstWhere(
        (game) => game.id == id,
        orElse: () => throw const ContractException('unknown fictional game'),
      );

  @override
  Future<Game> game(String id) async {
    probe.gameReads++;
    return _findGame(id);
  }

  @override
  Future<AttendanceSnapshot> attendance(String id) async {
    probe.attendanceReads++;
    _findGame(id);
    return AttendanceSnapshot(id, _ownReply, const [
      RepliedAttendance(
        'fictional-teammate',
        '虛構隊友',
        AttendanceReply.attending,
        AttendanceQualification.teamPlayer,
      ),
    ]);
  }

  @override
  Future<AttendanceReport> attendanceReport(
    String id, {
    int historyLimit = 12,
    int minimumResponseRate = 60,
  }) async {
    probe.reportReads++;
    _findGame(id);
    return AttendanceReport(
      gameId: id,
      generatedAt: DateTime.utc(2026, 8, 21, 8, 30),
      observation: AttendanceReportObservation(
        8,
        historyLimit,
        minimumResponseRate,
      ),
      attending: const [
        AttendanceReportPerson(
          'fictional-attending',
          '虛構出席隊員',
          AttendanceReply.attending,
        ),
      ],
      notAttending: const [
        AttendanceReportPerson(
          'fictional-not-attending',
          '虛構不出席隊員',
          AttendanceReply.notAttending,
        ),
      ],
      notYetReplied: const [
        AttendanceReportUnansweredPerson(
          personId: 'fictional-unanswered',
          displayName: '虛構尚未回覆隊員',
          observedReplies: 7,
          observedGames: 8,
          responseRate: 88,
          participationRate: 63,
          nonparticipationRate: 25,
        ),
      ],
    );
  }

  @override
  Future<MutationResult> reply(
    String gameId,
    AttendanceReply reply, {
    required bool online,
  }) async {
    if (!online) throw const OfflineReadOnlyException();
    probe.replyMutations++;
    _findGame(gameId);
    _ownReply = reply;
    return MutationResult(
      gameId,
      reply,
      true,
      DateTime.utc(2026, 8, 21, 8, 30),
      const MutationNotification(NotificationStatus.notRequired, null),
      false,
    );
  }
}

final _fictionalReportUiModel = SingleGameReportUiModel(
  gameId: 'game_901',
  gameLabel: '虛構校友隊 vs 範例友隊',
  generatedAt: DateTime.utc(2026, 8, 21, 8, 30),
  historyGames: 8,
  historyLimit: 12,
  minimumResponseRate: 60,
  attending: const [
    ReportParticipantUiModel(id: 'fictional-attending', displayName: '虛構出席隊員'),
  ],
  notAttending: const [
    ReportParticipantUiModel(
      id: 'fictional-not-attending',
      displayName: '虛構不出席隊員',
    ),
  ],
  notYetReplied: const [
    NotYetRepliedUiModel(
      id: 'fictional-unanswered',
      displayName: '虛構尚未回覆隊員',
      observedReplies: 7,
      observedGames: 8,
      responseRate: 88,
      participationRate: 63,
      nonparticipationRate: 25,
    ),
  ],
);

class _ProductionDemoReportCache implements PrincipalOfficerReportCache {
  _ProductionDemoReportCache(SingleGameReportUiModel report)
      : _reports = {'fictional-officer::${report.gameId}': report};

  final Map<String, SingleGameReportUiModel> _reports;

  String _key(String principalId, String gameId) => '$principalId::$gameId';

  @override
  Future<void> clearPrincipal(String principalId) async {
    _reports.removeWhere((key, _) => key.startsWith('$principalId::'));
  }

  @override
  Future<SingleGameReportUiModel?> read(
    String principalId,
    String gameId,
  ) async =>
      _reports[_key(principalId, gameId)];

  @override
  Future<void> write(String principalId, SingleGameReportUiModel report) async {
    _reports[_key(principalId, report.gameId)] = report;
  }
}
