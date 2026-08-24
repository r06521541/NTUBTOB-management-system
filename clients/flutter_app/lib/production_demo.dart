import 'dart:math';

import 'package:flutter/material.dart';

import 'app_theme.dart';
import 'basic_app.dart';
import 'foundation.dart';
import 'integration.dart';
import 'identity_link.dart';
import 'local_preferences.dart';
import 'officer_prereview.dart';
import 'notification_center.dart';
import 'pending_review.dart';

enum ProductionDemoPersona { basic, officer }

enum ProductionDemoConnectivity { online, offline }

enum ProductionDemoDataState { populated, resolved, actionError, empty, error }

enum ProductionDemoReplyScenario { normal, mutationError, uncertain }

enum ProductionDemoNotificationState { populated, empty, error }

enum ProductionDemoPublishScenario { success, previewError, confirmError }

class ProductionDemoProbe {
  int unexpectedTransportCalls = 0;
  int gameReads = 0;
  int attendanceReads = 0;
  int reportReads = 0;
  int replyMutations = 0;
  final previewDrafts = <Map<String, dynamic>>[];
  final previewRevisions = <String>[];
  final confirmDrafts = <Map<String, dynamic>>[];
  final confirmPreviews = <Map<String, dynamic>>[];
  final confirmKeys = <String>[];
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
    Game(
      'game_905',
      DateTime.utc(2026, 10, 5, 6),
      120,
      '虛構週界球場',
      '示意星期一隊',
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
        'notifications:publish',
      ],
      accessLevel: AccessLevel.officer);

  late final ProductionDemoProbe _probe;
  late final _ProductionDemoApi _api;
  late final _ProductionDemoReportCache _reportCache;
  late final NotificationCache _notificationCache;
  late final _ProductionDemoNotificationClient _notificationClient;
  late final _ProductionDemoPublishingClient _publishingClient;
  late final LocalPreferences _preferences;
  late final Future<void> _notificationSeedReady;
  final _notificationControllers = <String, NotificationCenterController>{};
  ProductionDemoPersona _persona = ProductionDemoPersona.basic;
  ProductionDemoConnectivity _connectivity = ProductionDemoConnectivity.online;
  ProductionDemoDataState _dataState = ProductionDemoDataState.populated;
  ProductionDemoReplyScenario _replyScenario =
      ProductionDemoReplyScenario.normal;
  ProductionDemoNotificationState _notificationState =
      ProductionDemoNotificationState.populated;
  ProductionDemoPublishScenario _publishScenario =
      ProductionDemoPublishScenario.success;

  @override
  void initState() {
    super.initState();
    _probe = widget.probe ?? ProductionDemoProbe();
    _api = _ProductionDemoApi(_probe, _games);
    _reportCache = _ProductionDemoReportCache(_fictionalReportUiModel);
    _notificationCache = NotificationCache(MemoryStore(), 'fictional-demo');
    _notificationClient = _ProductionDemoNotificationClient();
    _publishingClient = _ProductionDemoPublishingClient(_probe);
    _preferences = LocalPreferences(MemoryStore(), 'fictional-demo');
    _notificationSeedReady = _seedNotifications(_basicPerson);
  }

  Future<void> _seedNotifications(Person principal) async {
    final notifications = _notificationClient.values;
    await _notificationCache.save(
      principal,
      notifications,
      _lastSyncedAt,
      unreadCount: notifications.where((item) => !item.isRead).length,
    );
  }

  Future<void> _selectPersona(ProductionDemoPersona value) async {
    if (_persona == value) return;
    final principal =
        value == ProductionDemoPersona.basic ? _basicPerson : _officerPerson;
    await _seedNotifications(principal);
    _notificationControllers.clear();
    if (mounted) setState(() => _persona = value);
  }

  Future<void> _selectNotificationState(
    ProductionDemoNotificationState value,
  ) async {
    if (_notificationState == value) return;
    _notificationClient.configure(value);
    final principal =
        _persona == ProductionDemoPersona.basic ? _basicPerson : _officerPerson;
    await _seedNotifications(principal);
    _notificationControllers.clear();
    if (mounted) setState(() => _notificationState = value);
  }

  void _selectPublishScenario(ProductionDemoPublishScenario value) {
    _publishingClient.scenario = value;
    setState(() => _publishScenario = value);
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
    _api.actionScenario = _dataState;
    _api.replyScenario = _replyScenario;
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
                      _selectPersona(ProductionDemoPersona.basic),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-persona-officer'),
                  label: const Text('幹部'),
                  selected: _persona == ProductionDemoPersona.officer,
                  onSelected: (_) =>
                      _selectPersona(ProductionDemoPersona.officer),
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
                  key: const ValueKey('demo-data-resolved'),
                  label: const Text('待辦已處理'),
                  selected: _dataState == ProductionDemoDataState.resolved,
                  onSelected: (_) => setState(
                    () => _dataState = ProductionDemoDataState.resolved,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-data-action-error'),
                  label: const Text('待辦錯誤'),
                  selected: _dataState == ProductionDemoDataState.actionError,
                  onSelected: (_) => setState(
                    () => _dataState = ProductionDemoDataState.actionError,
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
                const SizedBox(width: 12),
                const Text('通知：'),
                ChoiceChip(
                  key: const ValueKey('demo-notifications-populated'),
                  label: const Text('有通知'),
                  selected: _notificationState ==
                      ProductionDemoNotificationState.populated,
                  onSelected: (_) => _selectNotificationState(
                    ProductionDemoNotificationState.populated,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-notifications-empty'),
                  label: const Text('通知空資料'),
                  selected: _notificationState ==
                      ProductionDemoNotificationState.empty,
                  onSelected: (_) => _selectNotificationState(
                    ProductionDemoNotificationState.empty,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-notifications-error'),
                  label: const Text('通知錯誤'),
                  selected: _notificationState ==
                      ProductionDemoNotificationState.error,
                  onSelected: (_) => _selectNotificationState(
                    ProductionDemoNotificationState.error,
                  ),
                ),
                const SizedBox(width: 12),
                const Text('發布：'),
                ChoiceChip(
                  key: const ValueKey('demo-publish-success'),
                  label: const Text('成功'),
                  selected:
                      _publishScenario == ProductionDemoPublishScenario.success,
                  onSelected: (_) => _selectPublishScenario(
                    ProductionDemoPublishScenario.success,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-publish-preview-error'),
                  label: const Text('預覽失敗'),
                  selected: _publishScenario ==
                      ProductionDemoPublishScenario.previewError,
                  onSelected: (_) => _selectPublishScenario(
                    ProductionDemoPublishScenario.previewError,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-publish-confirm-error'),
                  label: const Text('確認失敗'),
                  selected: _publishScenario ==
                      ProductionDemoPublishScenario.confirmError,
                  onSelected: (_) => _selectPublishScenario(
                    ProductionDemoPublishScenario.confirmError,
                  ),
                ),
                const SizedBox(width: 12),
                const Text('回覆：'),
                ChoiceChip(
                  key: const ValueKey('demo-reply-normal'),
                  label: const Text('正常'),
                  selected:
                      _replyScenario == ProductionDemoReplyScenario.normal,
                  onSelected: (_) => setState(
                    () => _replyScenario = ProductionDemoReplyScenario.normal,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-reply-mutation-error'),
                  label: const Text('回覆失敗'),
                  selected: _replyScenario ==
                      ProductionDemoReplyScenario.mutationError,
                  onSelected: (_) => setState(
                    () => _replyScenario =
                        ProductionDemoReplyScenario.mutationError,
                  ),
                ),
                const SizedBox(width: 4),
                ChoiceChip(
                  key: const ValueKey('demo-reply-uncertain'),
                  label: const Text('結果待確認'),
                  selected:
                      _replyScenario == ProductionDemoReplyScenario.uncertain,
                  onSelected: (_) => setState(
                    () =>
                        _replyScenario = ProductionDemoReplyScenario.uncertain,
                  ),
                ),
              ],
            ),
          ),
          Wrap(
            children: [
              TextButton(
                key: const ValueKey('demo-server-publish-flow-entry'),
                onPressed: _persona == ProductionDemoPersona.officer
                    ? () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => CanonicalManagementReportsPage(
                              api: _api,
                              person: _officerPerson,
                              games: games,
                              online: online,
                              cache: _reportCache,
                              publishingClient:
                                  online ? _publishingClient : null,
                            ),
                          ),
                        )
                    : null,
                child: const Text('伺服器形狀發布流程'),
              ),
              TextButton(
                key: const ValueKey('demo-account-link'),
                onPressed: () {
                  final controller = _demoIdentityLinkController(online);
                  controller.loadLinkedMethods();
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => Scaffold(
                        appBar: AppBar(title: const Text('虛構帳號管理')),
                        body: ListView(
                          padding: const EdgeInsets.all(16),
                          children: [
                            IdentityLinkPanel(
                              controller: controller,
                              platform: 'android',
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
                child: const Text('帳號連結情境'),
              ),
              TextButton(
                key: const ValueKey('demo-account-recovery'),
                onPressed: online
                    ? () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => IdentityRecoveryPage(
                              controller: _demoIdentityLinkController(true),
                              platform: 'android',
                            ),
                          ),
                        )
                    : null,
                child: const Text('陌生登入追認'),
              ),
              TextButton(
                key: const ValueKey('demo-pending-review'),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => PendingReviewPage(
                      client: PendingReviewClient(
                        _DemoReviewTransport(),
                        'fictional-review',
                        SecureIds(Random(149)),
                      ),
                    ),
                  ),
                ),
                child: const Text('待審核情境'),
              ),
              TextButton(
                key: const ValueKey('demo-settings'),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => LocalPreferencesPage(
                      preferences: _preferences,
                      permissions: const NotificationPermissionActions(
                        UnsupportedNotificationPermissionPort(),
                      ),
                      onThemeChanged: (_) {},
                    ),
                  ),
                ),
                child: const Text('設定情境'),
              ),
              TextButton(
                key: const ValueKey('demo-onboarding'),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (routeContext) => OnboardingPage(
                      onComplete: () async => Navigator.of(routeContext).pop(),
                    ),
                  ),
                ),
                child: const Text('新手引導情境'),
              ),
            ],
          ),
          const Divider(height: 1),
          Expanded(
            child: FutureBuilder<void>(
              future: _notificationSeedReady,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                return _dataState == ProductionDemoDataState.error
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
                      );
              },
            ),
          ),
        ],
      ),
    );
  }

  IdentityLinkController _demoIdentityLinkController(bool online) =>
      IdentityLinkController(
        transport: _DemoIdentityLinkTransport(_probe),
        credentials: _DemoIdentityCredentials(),
        installationId: 'fictional-demo-installation',
        ids: SecureIds(Random(157)),
        online: online,
        authorizedSend: (method, path, {body}) =>
            _DemoIdentityLinkTransport(_probe).send(method, path, body: body),
      );
}

class _DemoIdentityCredentials implements IdentityCredentialPort {
  @override
  Future<String?> authenticate(LoginProvider provider, {String? nonce}) async =>
      'fictional-${provider.name}-id-token';

  @override
  Future<void> clearPresentationState() async {}
}

class _DemoIdentityLinkTransport implements ApiTransport {
  _DemoIdentityLinkTransport(this.probe);
  final ProductionDemoProbe probe;

  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    if (method == 'GET' && path == '/auth/identities') {
      return const ApiResponse(200, {
        'items': [
          {
            'provider': 'line',
            'label': 'LINE',
            'linked_at': '2026-08-20T08:00:00Z',
          },
        ],
      });
    }
    if (path.contains('/candidates/')) {
      return const ApiResponse(201, {
        'candidate_credential': 'fictional-candidate',
      });
    }
    if (path.contains('/proofs/')) {
      return const ApiResponse(201, {
        'proof_credential': 'fictional-proof',
        'person': {'display_name': '虛構一般使用者'},
      });
    }
    if (path == '/auth/identity-link/confirm') {
      return const ApiResponse(200, {'status': 'linked', 'session': null});
    }
    if (path == '/auth/identity-link/cancel') {
      return const ApiResponse(204, null);
    }
    probe.unexpectedTransportCalls++;
    throw StateError('unexpected fictional identity transport');
  }
}

class _DemoReviewTransport implements ApiTransport {
  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    return const ApiResponse(200, {
      'status': 'pending',
      'messages': [
        {
          'id': 'message_1',
          'sender': 'admin',
          'body': '請補充球隊屆別。',
          'created_at': '2026-08-22T01:00:00Z',
          'redacted': false,
        },
      ],
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

class _ProductionDemoPublishingClient implements NotificationPublishingClient {
  _ProductionDemoPublishingClient(this.probe);

  final ProductionDemoProbe probe;
  ProductionDemoPublishScenario scenario =
      ProductionDemoPublishScenario.success;

  int _previewSequence = 0;
  Map<String, dynamic>? _previewDraft;
  Map<String, dynamic>? _previewResponse;

  Map<String, dynamic> _copy(Map<String, dynamic> value) => {
        for (final entry in value.entries)
          entry.key: entry.value is Map<String, dynamic>
              ? _copy(entry.value as Map<String, dynamic>)
              : entry.value is List
                  ? List.unmodifiable(entry.value as List<dynamic>)
                  : entry.value,
      };

  Map<String, dynamic> _freeze(Map<String, dynamic> value) =>
      Map.unmodifiable(_copy(value));

  Map<String, dynamic> _canonicalDraft(Map<String, dynamic> draft) {
    final audience = draft['audience'];
    if (audience is! Map<String, dynamic> || audience['type'] != 'individual') {
      throw const FormatException('fictional audience must be individual');
    }
    final personIds = audience['person_ids'];
    if (personIds is! List || personIds.isEmpty || personIds.length > 100) {
      throw const FormatException('fictional audience size is invalid');
    }
    final ids = <String>[];
    final seen = <String>{};
    for (final value in personIds) {
      if (value is! String ||
          !RegExp(r'^[a-z0-9][a-z0-9_-]{0,63}$').hasMatch(value) ||
          !seen.add(value)) {
        throw const FormatException('fictional audience ids are invalid');
      }
      ids.add(value);
    }
    return _freeze({
      ...draft,
      'audience': {'type': 'individual', 'person_ids': ids},
    });
  }

  bool _sameValue(Object? left, Object? right) {
    if (left is Map && right is Map) {
      return left.length == right.length &&
          left.keys.every(
            (key) =>
                right.containsKey(key) && _sameValue(left[key], right[key]),
          );
    }
    if (left is List && right is List) {
      return left.length == right.length &&
          Iterable.generate(left.length)
              .every((index) => _sameValue(left[index], right[index]));
    }
    return left == right;
  }

  bool _validKey(String key) =>
      RegExp(r'^[A-Za-z0-9_-]{16,200}$').hasMatch(key);

  @override
  Future<Map<String, dynamic>> preview(Map<String, dynamic> draft) async {
    final canonicalDraft = _canonicalDraft(draft);
    probe.previewDrafts.add(canonicalDraft);
    if (scenario == ProductionDemoPublishScenario.previewError) {
      throw StateError('fictional preview error');
    }
    final count =
        (canonicalDraft['audience'] as Map<String, dynamic>)['person_ids']
            .length;
    final revision = (++_previewSequence).toRadixString(16).padLeft(64, '0');
    final response = _freeze({
      'recipient_count': count,
      'revision': revision,
      'confirmation_text': 'PUBLISH $count',
    });
    _previewDraft = canonicalDraft;
    _previewResponse = response;
    probe.previewRevisions.add(revision);
    return response;
  }

  @override
  Future<Map<String, dynamic>> confirm(
    Map<String, dynamic> draft,
    Map<String, dynamic> preview,
    String key,
  ) async {
    final canonicalDraft = _canonicalDraft(draft);
    final canonicalPreview = _freeze(preview);
    probe.confirmDrafts.add(canonicalDraft);
    probe.confirmPreviews.add(canonicalPreview);
    probe.confirmKeys.add(key);
    final expectedDraft = _previewDraft;
    final expectedPreview = _previewResponse;
    if (expectedDraft == null ||
        expectedPreview == null ||
        !_sameValue(canonicalDraft, expectedDraft) ||
        canonicalPreview['recipient_count'] !=
            expectedPreview['recipient_count'] ||
        canonicalPreview['revision'] != expectedPreview['revision'] ||
        canonicalPreview['confirmation_text'] !=
            expectedPreview['confirmation_text'] ||
        !_validKey(key)) {
      throw const FormatException('fictional preview confirmation is stale');
    }
    if (scenario == ProductionDemoPublishScenario.confirmError) {
      throw StateError('fictional confirm error');
    }
    return const {'status': 'saved', 'outbox_status': 'pending'};
  }
}

class _ProductionDemoNotificationClient
    implements NotificationClient, PagedNotificationClient {
  List<MobileNotification> values = _populatedValues;
  ProductionDemoNotificationState _state =
      ProductionDemoNotificationState.populated;

  static final _populatedValues = [
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

  void configure(ProductionDemoNotificationState state) {
    _state = state;
    values = state == ProductionDemoNotificationState.empty
        ? const []
        : List.of(_populatedValues);
  }

  void _throwIfError() {
    if (_state == ProductionDemoNotificationState.error) {
      throw StateError('fictional notification retryable error');
    }
  }

  @override
  Future<MobileNotification> notification(String id) async {
    _throwIfError();
    return values.firstWhere((item) => item.id == id);
  }

  @override
  Future<List<MobileNotification>> notifications({
    bool unreadOnly = false,
  }) async {
    _throwIfError();
    return unreadOnly ? values.where((item) => !item.isRead).toList() : values;
  }

  @override
  Future<NotificationPage> page({
    String? cursor,
    bool unreadOnly = false,
  }) async {
    _throwIfError();
    final filtered =
        unreadOnly ? values.where((item) => !item.isRead).toList() : values;
    final index = cursor == null ? 0 : 1;
    if (index >= filtered.length) return const NotificationPage([], null);
    return NotificationPage([
      filtered[index],
    ], index + 1 < filtered.length ? 'fictional-next' : null);
  }

  @override
  Future<int> unreadCount() async {
    _throwIfError();
    return values.where((item) => !item.isRead).length;
  }

  @override
  Future<NotificationReadResult> markRead(String id) async {
    _throwIfError();
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
    _throwIfError();
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
  ProductionDemoDataState actionScenario = ProductionDemoDataState.populated;
  ProductionDemoReplyScenario replyScenario =
      ProductionDemoReplyScenario.normal;
  AttendanceReply _ownReply = AttendanceReply.undecided;

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
    if (actionScenario == ProductionDemoDataState.actionError) {
      throw const NetworkException();
    }
    final actionReply = actionScenario == ProductionDemoDataState.resolved
        ? AttendanceReply.attending
        : switch (id) {
            'game_901' => _ownReply,
            'game_902' => AttendanceReply.attending,
            'game_903' => null,
            _ => AttendanceReply.notAttending,
          };
    return AttendanceSnapshot(id, actionReply, const [
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
    final completeLineup = id == 'game_902';
    return AttendanceReport(
      gameId: id,
      generatedAt: DateTime.utc(2026, 8, 21, 8, 30),
      observation: AttendanceReportObservation(
        8,
        historyLimit,
        minimumResponseRate,
      ),
      attending: completeLineup
          ? List.generate(
              10,
              (index) => AttendanceReportPerson(
                'fictional-ready-$index',
                '虛構齊備隊員 ${index + 1}',
                index == 8
                    ? AttendanceReply.leavingEarly
                    : AttendanceReply.attending,
                memberNumber: index + 1,
              ),
            )
          : const [
              AttendanceReportPerson(
                'fictional-attending',
                '虛構出席隊員',
                AttendanceReply.arrivingLate,
                memberNumber: 18,
              ),
            ],
      notAttending: const [
        AttendanceReportPerson(
          'fictional-not-attending',
          '虛構不出席隊員',
          AttendanceReply.notAttending,
        ),
      ],
      notYetReplied: completeLineup
          ? const []
          : const [
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
    switch (replyScenario) {
      case ProductionDemoReplyScenario.mutationError:
        throw const NetworkException();
      case ProductionDemoReplyScenario.uncertain:
        throw MutationUncertainException(reply);
      case ProductionDemoReplyScenario.normal:
        break;
    }
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
    ReportParticipantUiModel(
      id: 'fictional-attending',
      displayName: '虛構出席隊員',
      memberNumber: 18,
      reply: AttendanceReply.arrivingLate,
    ),
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
