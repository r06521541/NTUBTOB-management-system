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

class BasicBootstrapApp extends StatefulWidget {
  const BasicBootstrapApp({super.key, required this.config});
  final AppConfig config;
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
  PrincipalOfficerReportCache? _reportCache;
  Person? person;
  List<Game> games = const [];
  DateTime? lastSyncedAt;
  PrincipalProvenance? principalProvenance;

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
      if (await _store.read('logout-pending:$installationId') == 'true') {
        setState(() => state = AuthViewState.logoutPending);
        await session.logout(line);
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

  Future<void> _loadBasic() async {
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
      if (!mounted) return;
      setState(() {
        person = loadedPerson;
        games = loadedGames;
        lastSyncedAt = syncedAt;
        principalProvenance = PrincipalProvenance.freshServer;
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
    });
  }

  Future<void> _logout() async {
    setState(() => state = AuthViewState.logoutPending);
    if (person case final current?) {
      await _reportCache?.clearPrincipal(current.id);
    }
    try {
      await _session!.logout(_line!);
      await _cache!.clear();
      if (!mounted) return;
      setState(() {
        person = null;
        games = const [];
        principalProvenance = null;
        state = AuthViewState.loggedOut;
      });
    } on Object {
      // logout_pending intentionally remains visible and blocks actions.
    }
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
          body: state == AuthViewState.authenticated ||
                  state == AuthViewState.offline
              ? BasicGamesView(
                  api: _api!,
                  person: person!,
                  games: games,
                  online: state == AuthViewState.authenticated,
                  lastSyncedAt: lastSyncedAt!,
                  principalProvenance: principalProvenance,
                  reportCache: _reportCache)
              : AuthStatePanel(state: state),
          floatingActionButton: state == AuthViewState.authenticated
              ? FloatingActionButton(
                  onPressed: _logout,
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

class BasicGamesView extends StatelessWidget {
  const BasicGamesView({
    super.key,
    required this.api,
    required this.person,
    required this.games,
    required this.online,
    required this.lastSyncedAt,
    this.principalProvenance,
    this.reportCache,
    this.diagnosticEnabled = true,
  });
  final BasicApi api;
  final Person person;
  final List<Game> games;
  final bool online;
  final DateTime lastSyncedAt;
  final PrincipalProvenance? principalProvenance;
  final PrincipalOfficerReportCache? reportCache;

  /// Test injection can disable the diagnostic, but cannot enable it in a
  /// release build because rendering is always additionally gated by
  /// [kDebugMode].
  final bool diagnosticEnabled;

  @override
  Widget build(BuildContext context) => Material(
          child: ListView(children: [
        if (!online)
          Semantics(
              key: const ValueKey('offline-read-only'),
              label: '離線唯讀，出席回覆已停用',
              child: const ListTile(
                  leading: Icon(Icons.cloud_off), title: Text('離線唯讀模式'))),
        ListTile(
            title: Text(person.displayName),
            subtitle: Text('最後同步：${lastSyncedAt.toIso8601String()}')),
        if (DebugPrincipalProjection.shouldRender(
            debugBuild: kDebugMode, diagnosticEnabled: diagnosticEnabled))
          DebugPrincipalProjection(
              person: person, provenance: principalProvenance),
        if (person.canReadAttendanceReport)
          ListTile(
            key: const ValueKey('management-report-entry'),
            leading: const Icon(Icons.assessment_outlined),
            title: const Text('出席報表'),
            subtitle: const Text('Officer／Admin 唯讀'),
            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => CanonicalManagementReportsPage(
                api: api,
                person: person,
                games: games,
                online: online,
                cache: reportCache,
              ),
            )),
          ),
        if (games.isEmpty)
          Semantics(
              key: const ValueKey('games-empty'),
              label: '目前沒有可顯示的賽事',
              child: const ListTile(
                  leading: Icon(Icons.event_busy),
                  title: Text('目前沒有賽事'),
                  subtitle: Text('有新賽事時會顯示在這裡。'))),
        for (final game in games)
          ListTile(
              key: ValueKey('game-${game.id}'),
              title:
                  Text('${game.homeTeam ?? '主隊'} vs ${game.awayTeam ?? '客隊'}'),
              subtitle: Text(game.startAt.toIso8601String()),
              trailing: const Icon(Icons.chevron_right),
              onTap: online
                  ? () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) =>
                          GameDetailPage(api: api, gameId: game.id)))
                  : null),
      ]));
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

class GameDetailPage extends StatefulWidget {
  const GameDetailPage({super.key, required this.api, required this.gameId});
  final BasicApi api;
  final String gameId;
  @override
  State<GameDetailPage> createState() => _GameDetailPageState();
}

class _GameDetailPageState extends State<GameDetailPage> {
  DetailViewState state = DetailViewState.loading;
  Game? game;
  AttendanceSnapshot? attendance;
  AttendanceReply? selected;

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
        state = DetailViewState.ready;
      });
    } on MutationPendingException catch (error) {
      if (!mounted) return;
      setState(() {
        selected = error.reply;
        state = DetailViewState.uncertain;
      });
    } on MutationUncertainException {
      if (mounted) setState(() => state = DetailViewState.uncertain);
    } on Object catch (error) {
      _fail(error, mutation: true);
    }
  }

  void _fail(Object error, {bool mutation = false}) {
    if (!mounted) return;
    setState(() => state = error is SessionExpiredException ||
            error is ApiError &&
                (error.code == ApiErrorCode.sessionExpired ||
                    error.code == ApiErrorCode.unauthenticated)
        ? DetailViewState.sessionExpired
        : error is ContractException
            ? DetailViewState.contractError
            : mutation
                ? DetailViewState.mutationError
                : DetailViewState.error);
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

  Widget _content() => ListView(padding: const EdgeInsets.all(16), children: [
        Text('${game!.homeTeam ?? '主隊'} vs ${game!.awayTeam ?? '客隊'}',
            style: Theme.of(context).textTheme.titleLarge),
        Text(game!.startAt.toIso8601String()),
        const SizedBox(height: 16),
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
