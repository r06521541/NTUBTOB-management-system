import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'foundation.dart';
import 'integration.dart';
import 'officer_prereview.dart';

String? nativePlatformName(TargetPlatform platform) => switch (platform) {
      TargetPlatform.android => 'android',
      TargetPlatform.iOS => 'ios',
      _ => null,
    };

enum AuthViewState {
  booting,
  loggedOut,
  providerActive,
  exchanging,
  identityPending,
  accountUnavailable,
  sessionExpired,
  cancelled,
  recoverableError,
  contractError,
  unavailable,
  timeoutUnresolved,
  logoutPending,
  offline,
  authenticated
}

enum PrincipalProvenance { freshServer, offlineCache }

AuthViewState classifyFailure(Object error, {required bool hasCache}) {
  if (error is NetworkException) {
    return hasCache ? AuthViewState.offline : AuthViewState.recoverableError;
  }
  if (error is SessionExpiredException ||
      error is ApiError &&
          (error.code == ApiErrorCode.sessionExpired ||
              error.code == ApiErrorCode.unauthenticated)) {
    return AuthViewState.sessionExpired;
  }
  if (error is StateError && error.message == 'signed out') {
    return AuthViewState.loggedOut;
  }
  return AuthViewState.contractError;
}

bool canStartLogout(AuthViewState state, {required bool basicLoadInProgress}) =>
    state == AuthViewState.authenticated && !basicLoadInProgress;

Future<void> runBasicLogoutIfAllowed({
  required AuthViewState state,
  required bool basicLoadInProgress,
  required Future<void> Function() logout,
}) async {
  if (!canStartLogout(
    state,
    basicLoadInProgress: basicLoadInProgress,
  )) {
    return;
  }
  await logout();
}

class AuthStatePanel extends StatelessWidget {
  const AuthStatePanel({super.key, required this.state});
  final AuthViewState state;
  @override
  Widget build(BuildContext context) {
    final (icon, label) = switch (state) {
      AuthViewState.booting => (Icons.sync, '正在安全啟動'),
      AuthViewState.loggedOut => (Icons.login, '請使用 LINE 安全登入'),
      AuthViewState.providerActive => (Icons.open_in_new, 'LINE 登入處理中'),
      AuthViewState.exchanging => (Icons.sync_lock, '正在交換安全工作階段'),
      AuthViewState.identityPending => (Icons.hourglass_top, '身分資料處理中，請稍後重試'),
      AuthViewState.accountUnavailable => (Icons.person_off, '此帳號目前無法使用行動版'),
      AuthViewState.sessionExpired => (Icons.timer_off, '登入已逾期，請重新登入'),
      AuthViewState.cancelled => (Icons.cancel_outlined, '已取消登入'),
      AuthViewState.recoverableError => (Icons.wifi_off, '連線暫時失敗，請稍後重試'),
      AuthViewState.contractError => (Icons.gpp_bad, '資料格式異常，已停止處理'),
      AuthViewState.unavailable => (Icons.mobile_off, '此裝置無法使用 LINE 登入'),
      AuthViewState.timeoutUnresolved => (
          Icons.hourglass_disabled,
          'LINE 登入已逾時，請關閉既有登入畫面後返回'
        ),
      AuthViewState.logoutPending => (Icons.logout, '登出同步中，暫停操作'),
      AuthViewState.offline => (Icons.cloud_off, '離線唯讀模式'),
      AuthViewState.authenticated => (Icons.verified_user_outlined, '已安全登入'),
    };
    return Semantics(
      label: label,
      liveRegion: true,
      child: Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (state == AuthViewState.booting ||
              state == AuthViewState.exchanging)
            const CircularProgressIndicator()
          else
            Icon(icon),
          const SizedBox(height: 12),
          Text(label),
        ]),
      ),
    );
  }
}

class CacheSessionAggregateProducer {
  const CacheSessionAggregateProducer._();

  static bool matches({
    required SessionController session,
    required BasicCache basicCache,
    required DurablePrincipalOfficerReportCache reportCache,
    required BasicApi api,
  }) =>
      identical(session.store, basicCache.store) &&
      identical(session.store, reportCache.store) &&
      identical(session.store, api.store) &&
      identical(session, api.session) &&
      session.installationId == basicCache.installationId &&
      session.installationId == reportCache.installationId &&
      session.installationId == api.installationId;

  static Future<CacheSessionAggregate?> observe({
    required SessionController session,
    required BasicCache basicCache,
    required DurablePrincipalOfficerReportCache reportCache,
    required BasicApi api,
  }) async {
    if (!matches(
      session: session,
      basicCache: basicCache,
      reportCache: reportCache,
      api: api,
    )) {
      return null;
    }
    try {
      return CacheSessionAggregate.resolve(
        sessionPresent: await session.observePresence(),
        basicCachePresent: await basicCache.observePresence(),
        officerReportCachePresent: await reportCache.observeAnyPresence(),
        pendingAttendanceIntentCount:
            await api.observePendingAttendanceIntentCount(),
      );
    } on Object {
      return null;
    }
  }
}

Future<CacheSessionAggregate?> completeTerminalLogout({
  required SessionController session,
  required BasicCache basicCache,
  required DurablePrincipalOfficerReportCache reportCache,
  required BasicApi api,
  required LineLoginPort line,
}) async {
  if (!CacheSessionAggregateProducer.matches(
    session: session,
    basicCache: basicCache,
    reportCache: reportCache,
    api: api,
  )) {
    return null;
  }
  CacheSessionAggregate? aggregate;
  try {
    await session.logout(
      line,
      purgeLocal: () async {
        await basicCache.clear();
        await reportCache.clearInstallation();
        await api.clearPendingAttendanceIntents();
        aggregate = await CacheSessionAggregateProducer.observe(
          session: session,
          basicCache: basicCache,
          reportCache: reportCache,
          api: api,
        );
        if (aggregate == null) {
          throw StateError('local purge observation unavailable');
        }
      },
    );
  } on Object {
    return null;
  }
  return aggregate;
}

class BasicBootstrapApp extends StatefulWidget {
  const BasicBootstrapApp({
    super.key,
    required this.config,
    this.diagnosticEnabled = true,
  });
  final AppConfig config;
  final bool diagnosticEnabled;
  @override
  State<BasicBootstrapApp> createState() => _BasicBootstrapAppState();
}

class _BasicBootstrapAppState extends State<BasicBootstrapApp> {
  final _store = SecureStore();
  final _ids = SecureIds();
  AuthViewState state = AuthViewState.booting;
  late final http.Client _http;
  LoginCoordinator? _login;
  SessionController? _session;
  BasicApi? _api;
  LineLoginPort? _line;
  BasicCache? _cache;
  DurablePrincipalOfficerReportCache? _reportCache;
  Person? person;
  List<Game> games = const [];
  DateTime? lastSyncedAt;
  PrincipalProvenance? principalProvenance;
  CacheSessionAggregate? cacheSessionAggregate;
  Future<void>? _basicLoadOperation;
  bool _basicLoadInProgress = false;

  @override
  void initState() {
    super.initState();
    _http = http.Client();
    _boot();
  }

  Future<void> _boot() async {
    try {
      final installationId = await _installationId();
      final transport = HttpApiTransport(widget.config.apiBaseUrl!, _http);
      final session =
          SessionController(transport, _store, installationId, _ids);
      final line = NativeLineLogin(widget.config.lineChannelId!);
      _session = session;
      _line = line;
      _api = BasicApi(session, _store, installationId, _ids);
      _cache = BasicCache(_store, installationId);
      _reportCache = DurablePrincipalOfficerReportCache(_store, installationId);
      _login = LoginCoordinator(line, transport, session, _ids, installationId);
      _login!.addListener(_onLoginStateChanged);
      if (await _store.containsKey('logout-pending:$installationId')) {
        setState(() {
          state = AuthViewState.logoutPending;
          cacheSessionAggregate = null;
        });
        final aggregate = await completeTerminalLogout(
          session: session,
          basicCache: _cache!,
          reportCache: _reportCache!,
          api: _api!,
          line: line,
        );
        if (aggregate == null || !mounted) return;
        setState(() {
          state = AuthViewState.loggedOut;
          cacheSessionAggregate = aggregate;
        });
        return;
      }
      await session.refresh();
      await _loadBasic();
    } on Object catch (error) {
      await _showFailure(error);
    }
  }

  Future<String> _installationId() async {
    const key = 'installation:v1';
    final existing = await _store.read(key);
    if (existing != null) return existing;
    final created = _ids.next();
    await _store.write(key, created);
    return created;
  }

  Future<void> _signIn() async {
    final platform = nativePlatformName(Theme.of(context).platform);
    if (platform == null) {
      setState(() => state = AuthViewState.unavailable);
      return;
    }
    final login = _login!;
    await login.login(platform);
    if (login.state == LoginState.authenticated) {
      await _loadBasic();
    }
  }

  void _onLoginStateChanged() {
    final login = _login;
    if (!mounted || login == null) return;
    final next = switch (login.state) {
      LoginState.providerActive => AuthViewState.providerActive,
      LoginState.exchanging => AuthViewState.exchanging,
      LoginState.cancelled => AuthViewState.cancelled,
      LoginState.unavailable => AuthViewState.unavailable,
      LoginState.timeoutUnresolved => AuthViewState.timeoutUnresolved,
      LoginState.timeoutResolved => AuthViewState.recoverableError,
      LoginState.identityPending => AuthViewState.identityPending,
      LoginState.accountUnavailable => AuthViewState.accountUnavailable,
      // _loadBasic owns the authenticated transition after /me and games load.
      LoginState.authenticated => state,
      LoginState.error ||
      LoginState.stale ||
      LoginState.duplicate =>
        AuthViewState.contractError,
      LoginState.idle => state,
    };
    setState(() => state = next);
  }

  Future<void> _loadBasic() {
    final existingOperation = _basicLoadOperation;
    if (existingOperation != null) return existingOperation;

    _basicLoadInProgress = true;
    if (mounted) setState(() {});
    late final Future<void> operation;
    operation = _loadBasicOnce().whenComplete(() {
      if (identical(_basicLoadOperation, operation)) {
        _basicLoadOperation = null;
        if (mounted) {
          setState(() => _basicLoadInProgress = false);
        } else {
          _basicLoadInProgress = false;
        }
      }
    });
    _basicLoadOperation = operation;
    return operation;
  }

  Future<void> _loadBasicOnce() async {
    try {
      final loadedPerson = await _api!.me();
      final loadedGames = await _api!.games();
      final syncedAt = DateTime.now().toUtc();
      final previous = await _cache!.load();
      await reconcileFreshReportPrincipal(
        cache: _reportCache!,
        previous: previous?.person,
        current: loadedPerson,
      );
      await _cache!.save(loadedPerson, loadedGames, syncedAt);
      final aggregate = await _observeCacheSessionAggregate();
      if (!mounted) return;
      setState(() {
        person = loadedPerson;
        games = loadedGames;
        lastSyncedAt = syncedAt;
        principalProvenance = PrincipalProvenance.freshServer;
        cacheSessionAggregate = aggregate;
        state = AuthViewState.authenticated;
      });
    } on Object catch (error) {
      await _showFailure(error);
    }
  }

  Future<void> _showFailure(Object error) async {
    final cached = _cache == null ? null : await _cache!.load();
    final classified = classifyFailure(error, hasCache: cached != null);
    if (classified == AuthViewState.sessionExpired && cached != null) {
      await _reportCache?.clearPrincipal(cached.person.id);
    }
    final aggregate = await _observeCacheSessionAggregate();
    if (!mounted) return;
    setState(() {
      if (classified == AuthViewState.offline) {
        person = cached!.person;
        games = cached.games;
        lastSyncedAt = cached.lastSyncedAt;
        principalProvenance = PrincipalProvenance.offlineCache;
        state = AuthViewState.offline;
      } else {
        principalProvenance = null;
        state = classified;
      }
      cacheSessionAggregate = aggregate;
    });
  }

  Future<void> _logout() => runBasicLogoutIfAllowed(
        state: state,
        basicLoadInProgress: _basicLoadInProgress,
        logout: _performLogout,
      );

  Future<void> _performLogout() async {
    setState(() {
      state = AuthViewState.logoutPending;
      cacheSessionAggregate = null;
    });
    final aggregate = await completeTerminalLogout(
      session: _session!,
      basicCache: _cache!,
      reportCache: _reportCache!,
      api: _api!,
      line: _line!,
    );
    if (aggregate == null || !mounted) return;
    setState(() {
      person = null;
      games = const [];
      principalProvenance = null;
      cacheSessionAggregate = aggregate;
      state = AuthViewState.loggedOut;
    });
  }

  Future<CacheSessionAggregate?> _observeCacheSessionAggregate() {
    if (!DebugCacheSessionComposition.shouldRender(
      debugBuild: kDebugMode,
      diagnosticEnabled: widget.diagnosticEnabled,
      aggregatePresent: true,
    )) {
      return Future.value();
    }
    final session = _session;
    final basicCache = _cache;
    final reportCache = _reportCache;
    final api = _api;
    if (session == null ||
        basicCache == null ||
        reportCache == null ||
        api == null) {
      return Future.value();
    }
    return CacheSessionAggregateProducer.observe(
      session: session,
      basicCache: basicCache,
      reportCache: reportCache,
      api: api,
    );
  }

  @override
  void dispose() {
    _login?.removeListener(_onLoginStateChanged);
    _login?.dispose();
    _http.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: '北商乙組籃球隊',
        theme: demoTheme(Brightness.light),
        darkTheme: demoTheme(Brightness.dark),
        home: Scaffold(
          appBar: AppBar(title: const Text('隊務系統')),
          body: DebugCacheSessionComposition(
            aggregate: cacheSessionAggregate,
            diagnosticEnabled: widget.diagnosticEnabled,
            child: state == AuthViewState.authenticated ||
                    state == AuthViewState.offline
                ? BasicGamesView(
                    api: _api!,
                    person: person!,
                    games: games,
                    online: state == AuthViewState.authenticated,
                    lastSyncedAt: lastSyncedAt!,
                    principalProvenance: principalProvenance,
                    reportCache: _reportCache,
                    onRefresh: _loadBasic,
                  )
                : AuthStatePanel(state: state),
          ),
          floatingActionButton: state == AuthViewState.authenticated
              ? FloatingActionButton(
                  onPressed: canStartLogout(
                    state,
                    basicLoadInProgress: _basicLoadInProgress,
                  )
                      ? _logout
                      : null,
                  tooltip: '登出',
                  child: const Icon(Icons.logout))
              : LoginActionButton(
                  state: state, onLogin: _login == null ? null : _signIn),
        ),
      );
}

class LoginActionButton extends StatelessWidget {
  const LoginActionButton(
      {super.key, required this.state, required this.onLogin});
  final AuthViewState state;
  final VoidCallback? onLogin;

  static const _retryableStates = {
    AuthViewState.loggedOut,
    AuthViewState.cancelled,
    AuthViewState.identityPending,
    AuthViewState.accountUnavailable,
    AuthViewState.sessionExpired,
    AuthViewState.recoverableError,
  };

  @override
  Widget build(BuildContext context) {
    if (!_retryableStates.contains(state)) return const SizedBox.shrink();
    return FloatingActionButton(
        onPressed: onLogin, tooltip: 'LINE 登入', child: const Icon(Icons.login));
  }
}

class BasicGamesView extends StatefulWidget {
  const BasicGamesView({
    super.key,
    required this.api,
    required this.person,
    required this.games,
    required this.online,
    required this.lastSyncedAt,
    this.principalProvenance,
    this.reportCache,
    this.onRefresh,
    this.diagnosticEnabled = true,
  });
  final BasicApi api;
  final Person person;
  final List<Game> games;
  final bool online;
  final DateTime lastSyncedAt;
  final PrincipalProvenance? principalProvenance;
  final PrincipalOfficerReportCache? reportCache;
  final Future<void> Function()? onRefresh;

  /// Test injection can disable the diagnostic, but cannot enable it in a
  /// release build because rendering is always additionally gated by
  /// [kDebugMode].
  final bool diagnosticEnabled;

  @override
  State<BasicGamesView> createState() => _BasicGamesViewState();
}

class _BasicGamesViewState extends State<BasicGamesView> {
  bool _refreshInProgress = false;

  Future<void> _refresh() async {
    final refresh = widget.onRefresh;
    if (!widget.online || refresh == null || _refreshInProgress) return;
    setState(() => _refreshInProgress = true);
    try {
      await refresh();
    } on Object {
      // The parent reload owns its canonical error/offline presentation. Keep
      // the button callback from surfacing a second unhandled UI exception.
    } finally {
      if (mounted) setState(() => _refreshInProgress = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = MaterialLocalizations.of(context);
    final orderedGames = List<Game>.of(widget.games)
      ..sort((left, right) {
        final byStart = left.startAt.compareTo(right.startAt);
        return byStart != 0 ? byStart : left.id.compareTo(right.id);
      });
    final content = Material(
        child: ListView(children: [
      if (!widget.online)
        Semantics(
            key: const ValueKey('offline-read-only'),
            label: '離線唯讀，出席回覆已停用',
            child: const ListTile(
                leading: Icon(Icons.cloud_off), title: Text('離線唯讀模式'))),
      ListTile(
          title: Text(widget.person.displayName),
          subtitle: Text(
              '最後同步：${localizations.formatFullDate(widget.lastSyncedAt.toLocal())} ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(widget.lastSyncedAt.toLocal()))}'),
          trailing: IconButton(
            key: const ValueKey('games-refresh'),
            tooltip: '重新整理賽事',
            onPressed:
                widget.online && widget.onRefresh != null && !_refreshInProgress
                    ? _refresh
                    : null,
            icon: _refreshInProgress
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
          )),
      ListTile(
        key: const ValueKey('account-data-status-entry'),
        leading: const Icon(Icons.account_circle_outlined),
        title: const Text('帳號與資料狀態'),
        subtitle: const Text('查看目前顯示的帳號與資料來源'),
        onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => AccountDataStatusPage(
            person: widget.person,
            lastSyncedAt: widget.lastSyncedAt,
            provenance: widget.principalProvenance,
          ),
        )),
      ),
      if (DebugPrincipalProjection.shouldRender(
          debugBuild: kDebugMode, diagnosticEnabled: widget.diagnosticEnabled))
        DebugPrincipalProjection(
            person: widget.person, provenance: widget.principalProvenance),
      if (widget.person.canReadAttendanceReport)
        ListTile(
          key: const ValueKey('management-report-entry'),
          leading: const Icon(Icons.assessment_outlined),
          title: const Text('出席報表'),
          subtitle: const Text('Officer／Admin 唯讀'),
          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => CanonicalManagementReportsPage(
              api: widget.api,
              person: widget.person,
              games: widget.games,
              online: widget.online,
              cache: widget.reportCache,
            ),
          )),
        ),
      if (orderedGames.isEmpty)
        Semantics(
            key: const ValueKey('games-empty'),
            label: '目前沒有可顯示的賽事',
            child: const ListTile(
                leading: Icon(Icons.event_busy),
                title: Text('目前沒有賽事'),
                subtitle: Text('有新賽事時會顯示在這裡。'))),
      for (final game in orderedGames)
        ListTile(
            key: ValueKey('game-${game.id}'),
            title: Text('${game.homeTeam ?? '主隊'} vs ${game.awayTeam ?? '客隊'}'),
            subtitle: Text(_formatGameMetadata(localizations, game)),
            trailing: const Icon(Icons.chevron_right),
            onTap: widget.online
                ? () => Navigator.of(context).push(MaterialPageRoute<void>(
                    builder: (_) =>
                        GameDetailPage(api: widget.api, gameId: game.id)))
                : null),
    ]));
    final scrollableGamesView = ScrollConfiguration(
        behavior: ScrollConfiguration.of(context)
            .copyWith(physics: const AlwaysScrollableScrollPhysics()),
        child: content);
    if (!widget.online || widget.onRefresh == null) return scrollableGamesView;
    return RefreshIndicator(
        key: const ValueKey('games-pull-refresh'),
        semanticsLabel: '下拉重新整理賽事',
        onRefresh: _refresh,
        child: scrollableGamesView);
  }
}

String _formatGameMetadata(MaterialLocalizations localizations, Game game) {
  final localStart = game.startAt.toLocal();
  final date = localizations.formatFullDate(localStart);
  final time =
      localizations.formatTimeOfDay(TimeOfDay.fromDateTime(localStart));
  final details = <String>['$date $time'];
  if (game.location != null && game.location!.isNotEmpty) {
    details.add(game.location!);
  }
  if (game.durationMinutes != null) {
    details.add('${game.durationMinutes} 分鐘');
  }
  return details.join('・');
}

class AccountDataStatusPage extends StatelessWidget {
  const AccountDataStatusPage({
    super.key,
    required this.person,
    required this.lastSyncedAt,
    this.provenance,
  });

  final Person person;
  final DateTime lastSyncedAt;
  final PrincipalProvenance? provenance;

  @override
  Widget build(BuildContext context) {
    final localizations = MaterialLocalizations.of(context);
    final localLastSyncedAt = lastSyncedAt.toLocal();
    final source = switch (provenance) {
      PrincipalProvenance.freshServer => '資料來源：伺服器同步資料',
      PrincipalProvenance.offlineCache => '資料來源：離線快取，唯讀且非權威',
      null => '資料來源未確認，請勿視為權威',
    };
    final description = switch (provenance) {
      PrincipalProvenance.freshServer => '目前顯示的是已由伺服器同步的資料。',
      PrincipalProvenance.offlineCache => '目前顯示的是本機離線快取；內容僅供查看，唯讀且非權威。',
      null => '目前無法確認資料來源；內容僅供查看，請勿視為權威。',
    };
    return Scaffold(
      appBar: AppBar(title: const Text('帳號與資料狀態')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Semantics(
            key: const ValueKey('account-display-name'),
            label: '目前帳號：${person.displayName}',
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.person_outline),
              title: Text(person.displayName),
              subtitle: const Text('目前顯示的帳號'),
            ),
          ),
          const Divider(),
          Semantics(
            key: const ValueKey('account-last-sync'),
            label:
                '最後同步：${localizations.formatFullDate(localLastSyncedAt)} ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(localLastSyncedAt))}',
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.schedule_outlined),
              title: const Text('最後同步'),
              subtitle: Text(
                  '${localizations.formatFullDate(localLastSyncedAt)} ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(localLastSyncedAt))}'),
            ),
          ),
          const Divider(),
          Semantics(
            key: const ValueKey('account-data-provenance'),
            label: '$source $description',
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(provenance == PrincipalProvenance.freshServer
                  ? Icons.cloud_done_outlined
                  : Icons.cloud_off),
              title: Text(source),
              subtitle: Text(description),
            ),
          ),
        ],
      ),
    );
  }
}

class DebugPrincipalProjection extends StatelessWidget {
  const DebugPrincipalProjection(
      {super.key, required this.person, required this.provenance});

  final Person person;
  final PrincipalProvenance? provenance;

  static bool shouldRender(
          {required bool debugBuild, required bool diagnosticEnabled}) =>
      debugBuild && diagnosticEnabled;

  static String localizedRole(AccessLevel accessLevel) => switch (accessLevel) {
        AccessLevel.basic => '一般使用者',
        AccessLevel.officer => '幹部',
        AccessLevel.admin => '系統管理者',
      };

  static (String, String) localizedProvenance(
          PrincipalProvenance? provenance) =>
      switch (provenance) {
        PrincipalProvenance.freshServer => ('fresh_server', '伺服器最新驗證'),
        PrincipalProvenance.offlineCache => ('offline_cache', '離線快取，非權威'),
        null => ('unknown', '來源未確認，非權威'),
      };

  @override
  Widget build(BuildContext context) {
    final role = localizedRole(person.accessLevel);
    final reportRead = person.canReadAttendanceReport ? '啟用' : '停用';
    final (provenanceToken, provenanceLabel) = localizedProvenance(provenance);
    return Semantics(
      key: const ValueKey('debug-principal-projection'),
      label:
          '偵錯權限投影：$role；報表讀取：$reportRead；來源：$provenanceToken（$provenanceLabel）',
      child: ListTile(
        leading: const Icon(Icons.bug_report_outlined),
        title: Text(role),
        subtitle:
            Text('報表讀取：$reportRead；來源：$provenanceToken（$provenanceLabel）'),
      ),
    );
  }
}

enum DetailViewState {
  loading,
  ready,
  mutating,
  error,
  mutationError,
  uncertain,
  contractError,
  sessionExpired
}

class DebugCacheSessionProjection extends StatelessWidget {
  const DebugCacheSessionProjection({
    super.key,
    required this.aggregate,
    this.diagnosticEnabled = true,
  });

  final CacheSessionAggregate aggregate;
  final bool diagnosticEnabled;

  static bool shouldRender({
    required bool debugBuild,
    required bool diagnosticEnabled,
  }) =>
      debugBuild && diagnosticEnabled;

  static String _presence(bool present) => present ? 'present' : 'absent';

  @override
  Widget build(BuildContext context) {
    if (!shouldRender(
      debugBuild: kDebugMode,
      diagnosticEnabled: diagnosticEnabled,
    )) {
      return const SizedBox.shrink();
    }
    return Semantics(
      key: const ValueKey('debug-cache-session-projection'),
      label: '偵錯本機狀態：session ${_presence(aggregate.sessionPresent)}；'
          'basic_cache ${_presence(aggregate.basicCachePresent)}；'
          'officer_report_cache '
          '${_presence(aggregate.officerReportCachePresent)}；'
          'pending_attendance_intent '
          '${_presence(aggregate.pendingAttendanceIntentPresent)}',
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Text(
          'session ${_presence(aggregate.sessionPresent)}；'
          'basic_cache ${_presence(aggregate.basicCachePresent)}；'
          'officer_report_cache '
          '${_presence(aggregate.officerReportCachePresent)}；'
          'pending_attendance_intent '
          '${_presence(aggregate.pendingAttendanceIntentPresent)}',
        ),
      ),
    );
  }
}

class DebugCacheSessionComposition extends StatelessWidget {
  const DebugCacheSessionComposition({
    super.key,
    required this.aggregate,
    required this.child,
    this.diagnosticEnabled = true,
  });

  final CacheSessionAggregate? aggregate;
  final Widget child;
  final bool diagnosticEnabled;

  static bool shouldRender({
    required bool debugBuild,
    required bool diagnosticEnabled,
    required bool aggregatePresent,
  }) =>
      debugBuild && diagnosticEnabled && aggregatePresent;

  @override
  Widget build(BuildContext context) {
    final showDiagnostic = shouldRender(
      debugBuild: kDebugMode,
      diagnosticEnabled: diagnosticEnabled,
      aggregatePresent: aggregate != null,
    );
    if (!showDiagnostic) return child;
    return Column(
      children: [
        DebugCacheSessionProjection(aggregate: aggregate!),
        Expanded(child: child),
      ],
    );
  }
}

enum AuthoritativeOwnReplySource { freshServerGet, mutationReadback }

enum CanonicalOwnReplyObservation {
  none('none'),
  undecided('undecided'),
  attending('attending'),
  notAttending('not_attending'),
  arrivingLate('arriving_late'),
  leavingEarly('leaving_early');

  const CanonicalOwnReplyObservation(this.token);

  final String token;

  static CanonicalOwnReplyObservation fromReply(AttendanceReply? reply) =>
      switch (reply) {
        null => CanonicalOwnReplyObservation.none,
        AttendanceReply.undecided => CanonicalOwnReplyObservation.undecided,
        AttendanceReply.attending => CanonicalOwnReplyObservation.attending,
        AttendanceReply.notAttending =>
          CanonicalOwnReplyObservation.notAttending,
        AttendanceReply.arrivingLate =>
          CanonicalOwnReplyObservation.arrivingLate,
        AttendanceReply.leavingEarly =>
          CanonicalOwnReplyObservation.leavingEarly,
      };
}

class GameDetailPage extends StatefulWidget {
  const GameDetailPage({
    super.key,
    required this.api,
    required this.gameId,
    this.diagnosticEnabled = true,
  });
  final BasicApi api;
  final String gameId;
  final bool diagnosticEnabled;
  @override
  State<GameDetailPage> createState() => _GameDetailPageState();
}

class _GameDetailPageState extends State<GameDetailPage> {
  DetailViewState state = DetailViewState.loading;
  Game? game;
  AttendanceSnapshot? attendance;
  AttendanceReply? selected;
  AttendanceReply? authoritativeOwnReply;
  AuthoritativeOwnReplySource? authoritativeOwnReplySource;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final loadedGame = await widget.api.game(widget.gameId);
      final loadedAttendance = await widget.api.attendance(widget.gameId);
      if (!mounted) return;
      setState(() {
        game = loadedGame;
        attendance = loadedAttendance;
        selected = loadedAttendance.ownReply;
        authoritativeOwnReply = loadedAttendance.ownReply;
        authoritativeOwnReplySource =
            AuthoritativeOwnReplySource.freshServerGet;
        state = DetailViewState.ready;
      });
    } on Object catch (error) {
      _fail(error);
    }
  }

  Future<void> _submit() async {
    if (selected == null) return;
    setState(() => state = DetailViewState.mutating);
    try {
      await widget.api.reply(widget.gameId, selected!, online: true);
      final loaded = await widget.api.attendance(widget.gameId);
      if (!mounted) return;
      setState(() {
        attendance = loaded;
        selected = loaded.ownReply;
        authoritativeOwnReply = loaded.ownReply;
        authoritativeOwnReplySource =
            AuthoritativeOwnReplySource.mutationReadback;
        state = DetailViewState.ready;
      });
    } on MutationPendingException catch (error) {
      if (!mounted) return;
      setState(() {
        selected = error.reply;
        authoritativeOwnReply = null;
        authoritativeOwnReplySource = null;
        state = DetailViewState.uncertain;
      });
    } on MutationUncertainException {
      if (mounted) {
        setState(() {
          authoritativeOwnReply = null;
          authoritativeOwnReplySource = null;
          state = DetailViewState.uncertain;
        });
      }
    } on Object catch (error) {
      _fail(error, mutation: true);
    }
  }

  void _fail(Object error, {bool mutation = false}) {
    if (!mounted) return;
    setState(() {
      authoritativeOwnReply = null;
      authoritativeOwnReplySource = null;
      state = error is SessionExpiredException ||
              error is ApiError &&
                  (error.code == ApiErrorCode.sessionExpired ||
                      error.code == ApiErrorCode.unauthenticated)
          ? DetailViewState.sessionExpired
          : error is ContractException
              ? DetailViewState.contractError
              : mutation
                  ? DetailViewState.mutationError
                  : DetailViewState.error;
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('賽事與出席')),
        body: switch (state) {
          DetailViewState.loading => const Center(
              child: CircularProgressIndicator(semanticsLabel: '載入賽事與出席')),
          DetailViewState.error =>
            const AuthStatePanel(state: AuthViewState.recoverableError),
          DetailViewState.mutationError => Semantics(
              key: const ValueKey('mutation-error'),
              label: '出席回覆失敗，未變更目前結果',
              liveRegion: true,
              child: const Center(child: Text('出席回覆失敗，請確認狀態後重試。'))),
          DetailViewState.contractError =>
            const AuthStatePanel(state: AuthViewState.contractError),
          DetailViewState.sessionExpired =>
            const AuthStatePanel(state: AuthViewState.sessionExpired),
          _ => _content(),
        },
      );

  Widget _content() {
    final localizations = MaterialLocalizations.of(context);
    final observation = DebugAuthoritativeOwnReplyProjection.canonicalReply(
      reply: authoritativeOwnReply,
      detailReady: state == DetailViewState.ready,
      freshServerGet: authoritativeOwnReplySource ==
          AuthoritativeOwnReplySource.freshServerGet,
      mutationReadback: authoritativeOwnReplySource ==
          AuthoritativeOwnReplySource.mutationReadback,
    );
    return ListView(padding: const EdgeInsets.all(16), children: [
      Text('${game!.homeTeam ?? '主隊'} vs ${game!.awayTeam ?? '客隊'}',
          style: Theme.of(context).textTheme.titleLarge),
      Text(_formatGameMetadata(localizations, game!),
          key: const ValueKey('game-detail-metadata')),
      const SizedBox(height: 16),
      if (observation != null &&
          DebugAuthoritativeOwnReplyProjection.shouldRender(
            debugBuild: kDebugMode,
            diagnosticEnabled: widget.diagnosticEnabled,
          ))
        DebugAuthoritativeOwnReplyProjection(
          observation: observation.$1,
          source: observation.$2,
        ),
      const Text('我的出席回覆'),
      if (state == DetailViewState.uncertain)
        Semantics(
            key: const ValueKey('mutation-uncertain'),
            label: '回覆結果待確認，已保留同一操作識別碼',
            liveRegion: true,
            child: const Text('回覆結果待確認，請稍後以同一回覆重試。')),
      Wrap(
          spacing: 8,
          children: AttendanceReply.values
              .map((reply) => ChoiceChip(
                  key: ValueKey('reply-${reply.wire}'),
                  label: Text(_replyLabel(reply)),
                  selected: selected == reply,
                  onSelected: state == DetailViewState.mutating
                      ? null
                      : (_) => setState(() => selected = reply)))
              .toList()),
      FilledButton(
          onPressed: state == DetailViewState.mutating ? null : _submit,
          child: Text(state == DetailViewState.mutating ? '送出中' : '送出回覆')),
      const Divider(),
      const Text('已回覆隊員'),
      for (final reply in attendance!.replied)
        ListTile(
            title: Text(reply.displayName),
            subtitle: Text(
                '${_qualificationLabel(reply.qualification)}・${_replyLabel(reply.reply)}')),
    ]);
  }
}

class DebugAuthoritativeOwnReplyProjection extends StatelessWidget {
  const DebugAuthoritativeOwnReplyProjection({
    super.key,
    required this.observation,
    required this.source,
  });

  final CanonicalOwnReplyObservation observation;
  final AuthoritativeOwnReplySource source;

  static bool shouldRender({
    required bool debugBuild,
    required bool diagnosticEnabled,
  }) =>
      debugBuild && diagnosticEnabled;

  static (CanonicalOwnReplyObservation, AuthoritativeOwnReplySource)?
      canonicalReply({
    required AttendanceReply? reply,
    required bool detailReady,
    required bool freshServerGet,
    required bool mutationReadback,
  }) {
    if (!detailReady) return null;
    final sources = <AuthoritativeOwnReplySource>[
      if (freshServerGet) AuthoritativeOwnReplySource.freshServerGet,
      if (mutationReadback) AuthoritativeOwnReplySource.mutationReadback,
    ];
    return sources.length == 1
        ? (CanonicalOwnReplyObservation.fromReply(reply), sources.single)
        : null;
  }

  String get _sourceToken => switch (source) {
        AuthoritativeOwnReplySource.freshServerGet => 'fresh_server_get',
        AuthoritativeOwnReplySource.mutationReadback => 'mutation_readback',
      };

  @override
  Widget build(BuildContext context) => Semantics(
        key: const ValueKey('debug-authoritative-own-reply-projection'),
        label: '偵錯權威出席回覆：${observation.token}；來源：$_sourceToken',
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Text('${observation.token}；$_sourceToken'),
        ),
      );
}

String _replyLabel(AttendanceReply reply) => switch (reply) {
      AttendanceReply.attending => '出席',
      AttendanceReply.notAttending => '不出席',
      AttendanceReply.arrivingLate => '晚到',
      AttendanceReply.leavingEarly => '早退',
      AttendanceReply.undecided => '未決定',
    };

String _qualificationLabel(AttendanceQualification value) => switch (value) {
      AttendanceQualification.teamPlayer => '隊員',
      AttendanceQualification.guestPlayer => '友隊球員',
    };
