import 'package:flutter/foundation.dart' show defaultTargetPlatform, kDebugMode;
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_theme.dart';
import 'integration.dart';
import 'identity_link.dart';
import 'local_preferences.dart';
import 'notification_center.dart';
import 'pending_review.dart';
import 'support_app_info.dart';
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
  authenticated,
}

enum PrincipalProvenance { freshServer, offlineCache }

class AuthOperationContext {
  const AuthOperationContext(this.epoch, this.personId);
  final int epoch;
  final String? personId;

  bool matches({
    required int currentEpoch,
    required String? currentPersonId,
  }) =>
      epoch == currentEpoch && personId == currentPersonId;
}

AuthViewState classifyFailure(Object error, {required bool hasCache}) {
  if (error is NetworkException) {
    return hasCache ? AuthViewState.offline : AuthViewState.recoverableError;
  }
  if (isTerminalSessionFailure(error)) {
    return AuthViewState.sessionExpired;
  }
  if (error is StateError && error.message == 'signed out') {
    return AuthViewState.loggedOut;
  }
  return AuthViewState.contractError;
}

bool isTerminalSessionFailure(Object error) =>
    error is SessionExpiredException ||
    error is ApiError &&
        (error.code == ApiErrorCode.sessionExpired ||
            error.code == ApiErrorCode.unauthenticated);

bool canStartLogout(AuthViewState state, {required bool basicLoadInProgress}) =>
    state == AuthViewState.authenticated && !basicLoadInProgress;

Future<void> runBasicLogoutIfAllowed({
  required AuthViewState state,
  required bool basicLoadInProgress,
  required Future<void> Function() logout,
}) async {
  if (!canStartLogout(state, basicLoadInProgress: basicLoadInProgress)) {
    return;
  }
  await logout();
}

String? pendingReviewCredential(
  LoginCoordinator? line,
  GoogleLoginCoordinator? google,
) =>
    line?.pendingReview?.credential ?? google?.pendingReview?.credential;

bool shouldOfferIdentityRecovery({
  required AuthViewState state,
  required String? pendingReviewCredential,
}) =>
    state == AuthViewState.identityPending && pendingReviewCredential == null;

class AuthStatePanel extends StatelessWidget {
  const AuthStatePanel({
    super.key,
    required this.state,
    this.onRecoverIdentity,
  });
  final AuthViewState state;
  final VoidCallback? onRecoverIdentity;
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
          'LINE 登入已逾時，請關閉既有登入畫面後返回',
        ),
      AuthViewState.logoutPending => (Icons.logout, '登出同步中，暫停操作'),
      AuthViewState.offline => (Icons.cloud_off, '離線唯讀模式'),
      AuthViewState.authenticated => (Icons.verified_user_outlined, '已安全登入'),
    };
    return Semantics(
      label: label,
      liveRegion: true,
      child: Center(
        child: SizedBox(
          width: 320,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            AppStatusPanel(
              icon: icon,
              title: label,
              loading: state == AuthViewState.booting ||
                  state == AuthViewState.exchanging,
              liveRegion: true,
            ),
            if (state == AuthViewState.identityPending &&
                onRecoverIdentity != null)
              TextButton(
                key: const ValueKey('identity-recovery-entry'),
                onPressed: onRecoverIdentity,
                child: const Text('我曾用其他方式登入'),
              ),
          ]),
        ),
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
  required NotificationCache notificationCache,
  required DurablePrincipalOfficerReportCache reportCache,
  required BasicApi api,
  required LineLoginPort line,
}) async {
  if (!CacheSessionAggregateProducer.matches(
        session: session,
        basicCache: basicCache,
        reportCache: reportCache,
        api: api,
      ) ||
      !identical(session.store, notificationCache.store) ||
      session.installationId != notificationCache.installationId) {
    return null;
  }
  CacheSessionAggregate? aggregate;
  try {
    await session.logout(
      line,
      purgeLocal: () async {
        await basicCache.clear();
        await notificationCache.clear();
        await reportCache.clearInstallation();
        await api.clearPendingAttendanceIntents();
        await api.clearPendingProfileIntents();
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
    this.store,
    this.permissionPort = const UnsupportedNotificationPermissionPort(),
  });
  final AppConfig config;
  final bool diagnosticEnabled;
  final DurableStore? store;
  final NotificationPermissionPort permissionPort;
  @override
  State<BasicBootstrapApp> createState() => _BasicBootstrapAppState();
}

class _BasicBootstrapAppState extends State<BasicBootstrapApp> {
  late final DurableStore _store;
  final _ids = SecureIds();
  AuthViewState state = AuthViewState.booting;
  late final http.Client _http;
  LoginCoordinator? _login;
  GoogleLoginCoordinator? _googleLogin;
  SessionController? _session;
  BasicApi? _api;
  LineLoginPort? _line;
  GoogleLoginPort? _google;
  IdentityLinkController? _identityLink;
  BasicCache? _cache;
  NotificationCache? _notificationCache;
  DurablePrincipalOfficerReportCache? _reportCache;
  NotificationCenterController? _notificationController;
  Person? person;
  List<Game> games = const [];
  DateTime? lastSyncedAt;
  PrincipalProvenance? principalProvenance;
  CacheSessionAggregate? cacheSessionAggregate;
  Future<bool>? _basicLoadOperation;
  bool _basicLoadInProgress = false;
  int _authEpoch = 0;
  final _navigatorKey = GlobalKey<NavigatorState>();
  PendingReviewClient? _pendingReviewClient;
  LocalPreferences? _preferences;
  LocalThemePreference _themePreference = LocalThemePreference.system;
  bool? _onboardingComplete;

  @override
  void initState() {
    super.initState();
    _store = widget.store ?? SecureStore();
    _http = http.Client();
    _boot();
  }

  Future<void> _boot() async {
    try {
      final installationId = await _installationId();
      final preferences = LocalPreferences(_store, installationId);
      final themePreference = await preferences.theme();
      final onboardingComplete = await preferences.onboardingComplete();
      if (!mounted) return;
      setState(() {
        _preferences = preferences;
        _themePreference = themePreference;
        _onboardingComplete = onboardingComplete;
      });
      final transport = HttpApiTransport(widget.config.apiBaseUrl!, _http);
      final notificationCache = NotificationCache(_store, installationId);
      final session = SessionController(
        transport,
        _store,
        installationId,
        _ids,
        terminalPurge: notificationCache.clear,
      );
      final line = NativeLineLogin(widget.config.lineChannelId!);
      final google = NativeGoogleLogin(
        nativePlatformName(defaultTargetPlatform) ?? '',
        widget.config.googleClientId!,
        widget.config.googleServerClientId!,
      );
      _session = session;
      _line = line;
      _google = google;
      _identityLink = IdentityLinkController(
        transport: transport,
        credentials: NativeIdentityCredentialPort(line, google),
        installationId: installationId,
        ids: _ids,
        session: session,
        onRecovered: _loadBasic,
        onTerminalSession: () => _showFailure(const SessionExpiredException()),
      );
      _api = BasicApi(session, _store, installationId, _ids);
      _cache = BasicCache(_store, installationId);
      _notificationCache = notificationCache;
      _reportCache = DurablePrincipalOfficerReportCache(_store, installationId);
      _login = LoginCoordinator(line, transport, session, _ids, installationId);
      _googleLogin = GoogleLoginCoordinator(
        google,
        transport,
        session,
        _ids,
        installationId,
      );
      _login!.addListener(_onLoginStateChanged);
      _googleLogin!.addListener(_onGoogleLoginStateChanged);
      if (await _store.containsKey('logout-pending:$installationId')) {
        setState(() {
          state = AuthViewState.logoutPending;
          cacheSessionAggregate = null;
        });
        final aggregate = await completeTerminalLogout(
          session: session,
          basicCache: _cache!,
          notificationCache: notificationCache,
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
    _authEpoch++;
    _basicLoadOperation = null;
    _basicLoadInProgress = false;
    _retirePendingReview();
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

  Future<void> _signInGoogle() async {
    _authEpoch++;
    _basicLoadOperation = null;
    _basicLoadInProgress = false;
    _retirePendingReview();
    final platform = nativePlatformName(Theme.of(context).platform);
    if (platform == null) {
      setState(() => state = AuthViewState.unavailable);
      return;
    }
    final login = _googleLogin!;
    await login.login(platform);
    if (login.state == LoginState.authenticated) await _loadBasic();
  }

  void _onGoogleLoginStateChanged() {
    final login = _googleLogin;
    if (!mounted || login == null) return;
    final next = switch (login.state) {
      LoginState.providerActive => AuthViewState.providerActive,
      LoginState.exchanging => AuthViewState.exchanging,
      LoginState.cancelled => AuthViewState.cancelled,
      LoginState.unavailable => AuthViewState.unavailable,
      LoginState.identityPending => AuthViewState.identityPending,
      LoginState.accountUnavailable => AuthViewState.accountUnavailable,
      LoginState.authenticated || LoginState.idle => state,
      _ => AuthViewState.contractError,
    };
    setState(() => state = next);
    if (next == AuthViewState.identityPending && login.pendingReview != null) {
      _openPendingReview();
    } else if (next != AuthViewState.identityPending) {
      _retirePendingReview();
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
    if (next == AuthViewState.identityPending && login.pendingReview != null) {
      _openPendingReview();
    } else if (next != AuthViewState.identityPending) {
      _retirePendingReview();
    }
  }

  void _openPendingReview() {
    final credential = pendingReviewCredential(_login, _googleLogin);
    if (credential == null || !mounted) return;
    final client = PendingReviewClient(
      HttpApiTransport(widget.config.apiBaseUrl!, _http),
      credential,
      _ids,
    );
    _pendingReviewClient = client;
    _navigatorKey.currentState?.push(MaterialPageRoute<void>(
      builder: (_) => PendingReviewPage(
        client: client,
      ),
    ));
  }

  void _retirePendingReview() {
    _login?.retirePendingReview();
    _googleLogin?.retirePendingReview();
    _pendingReviewClient?.retire();
    _pendingReviewClient = null;
    _navigatorKey.currentState?.popUntil((route) => route.isFirst);
  }

  Future<void> _openIdentityRecovery() async {
    final controller = _identityLink;
    final platform = nativePlatformName(Theme.of(context).platform);
    if (controller == null || platform == null || !mounted) return;
    final result = await _navigatorKey.currentState?.push<IdentityLinkStage>(
      MaterialPageRoute<IdentityLinkStage>(
        builder: (_) => IdentityRecoveryPage(
          controller: controller,
          platform: platform,
        ),
      ),
    );
    if (mounted && result == IdentityLinkStage.reauthenticationRequired) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('登入方式已連結，請重新正常登入。')),
      );
    } else if (mounted && result == IdentityLinkStage.error) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('連結流程失敗，請重新開始。')),
      );
    }
  }

  Future<bool> _loadBasic() {
    final existingOperation = _basicLoadOperation;
    if (existingOperation != null) return existingOperation;

    _basicLoadInProgress = true;
    if (mounted) setState(() {});
    late final Future<bool> operation;
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

  Future<bool> _loadBasicOnce() async {
    final epoch = _authEpoch;
    final operation = AuthOperationContext(epoch, person?.id);
    try {
      final loadedPerson = await _api!.me();
      if (!operation.matches(
        currentEpoch: _authEpoch,
        currentPersonId: person?.id,
      )) {
        return false;
      }
      final loadedGames = await _api!.games();
      if (epoch != _authEpoch) return false;
      final syncedAt = DateTime.now().toUtc();
      final previous = await _cache!.load();
      if (epoch != _authEpoch) return false;
      if ((person != null && person!.id != loadedPerson.id) ||
          (previous != null && previous.person.id != loadedPerson.id)) {
        await _identityLink?.personSwitch();
        _navigatorKey.currentState?.popUntil((route) => route.isFirst);
        if (epoch != _authEpoch) return false;
      }
      if (previous != null &&
          (previous.person.id != loadedPerson.id ||
              previous.person.accessLevel != loadedPerson.accessLevel ||
              previous.person.capabilities.length !=
                  loadedPerson.capabilities.length ||
              previous.person.capabilities.any((capability) =>
                  !loadedPerson.capabilities.contains(capability)))) {
        await _api!.clearPendingProfileIntents();
        if (epoch != _authEpoch) return false;
      }
      await reconcileFreshReportPrincipal(
        cache: _reportCache!,
        previous: previous?.person,
        current: loadedPerson,
      );
      if (epoch != _authEpoch) return false;
      await _notificationCache!.reconcileFreshPrincipal(
        previous?.person,
        loadedPerson,
      );
      if (epoch != _authEpoch) return false;
      if (_notificationController?.principal.id != loadedPerson.id) {
        await _notificationController?.invalidate();
        _notificationController = null;
      }
      if (!loadedPerson.canReadNotifications) {
        await _notificationController?.invalidate();
        _notificationController = null;
      }
      final committed = await _cache!.saveFenced(
        loadedPerson,
        loadedGames,
        syncedAt,
        generation: epoch,
        isCurrent: () => epoch == _authEpoch,
      );
      if (!committed) return false;
      final aggregate = await _observeCacheSessionAggregate();
      if (!mounted || epoch != _authEpoch) return false;
      setState(() {
        person = loadedPerson;
        games = loadedGames;
        lastSyncedAt = syncedAt;
        principalProvenance = PrincipalProvenance.freshServer;
        cacheSessionAggregate = aggregate;
        state = AuthViewState.authenticated;
      });
      return true;
    } on Object catch (error) {
      if (epoch != _authEpoch) return false;
      await _showFailure(error);
      return false;
    }
  }

  Future<void> _showFailure(Object error) async {
    final cached = _cache == null ? null : await _cache!.load();
    final classified = classifyFailure(error, hasCache: cached != null);
    if (classified == AuthViewState.sessionExpired) {
      _authEpoch++;
      _retirePendingReview();
      await _identityLink?.terminal();
      _navigatorKey.currentState?.popUntil((route) => route.isFirst);
      await _api?.clearPendingProfileIntents();
      await _cache?.clear();
    }
    if (classified == AuthViewState.sessionExpired && cached != null) {
      await _reportCache?.clearPrincipal(cached.person.id);
    }
    if (classified == AuthViewState.sessionExpired) {
      await _notificationController?.invalidate();
      _notificationController = null;
      await _notificationCache?.clear();
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
        person = null;
        games = const [];
        lastSyncedAt = null;
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
    _authEpoch++;
    _retirePendingReview();
    await _identityLink?.terminal();
    await _notificationController?.invalidate();
    _notificationController = null;
    try {
      await _google?.logout();
    } on Object {
      // Local app-session terminal state must not be blocked by provider UI.
    }
    setState(() {
      state = AuthViewState.logoutPending;
      cacheSessionAggregate = null;
    });
    final aggregate = await completeTerminalLogout(
      session: _session!,
      basicCache: _cache!,
      notificationCache: _notificationCache!,
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
    _googleLogin?.removeListener(_onGoogleLoginStateChanged);
    _googleLogin?.dispose();
    _http.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        navigatorKey: _navigatorKey,
        title: '北商乙組籃球隊',
        theme: appTheme(Brightness.light),
        darkTheme: appTheme(Brightness.dark),
        themeMode: _themePreference.themeMode,
        home: _onboardingComplete == false
            ? OnboardingPage(onComplete: _completeOnboarding)
            : Scaffold(
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
                          notificationController:
                              _notificationControllerFor(person!),
                          onRefresh: _loadBasic,
                          onPersonUpdated: _profileUpdateCallback(),
                          onProfileTerminalSession:
                              _handleProfileTerminalSession,
                          onOpenSettings: _openSettings,
                          identityLink: _identityLink,
                          platform:
                              nativePlatformName(Theme.of(context).platform),
                        )
                      : AuthStatePanel(
                          state: state,
                          onRecoverIdentity: shouldOfferIdentityRecovery(
                                  state: state,
                                  pendingReviewCredential:
                                      pendingReviewCredential(
                                          _login, _googleLogin))
                              ? _openIdentityRecovery
                              : null,
                        ),
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
                        child: const Icon(Icons.logout),
                      )
                    : LoginActionButton(
                        state: state,
                        onLogin: _login == null ? null : _signIn,
                        onGoogleLogin:
                            _googleLogin == null ? null : _signInGoogle,
                      ),
              ),
      );

  Future<void> _completeOnboarding() async {
    await _preferences!.completeOnboarding();
    if (mounted) setState(() => _onboardingComplete = true);
  }

  void _openSettings() {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => LocalPreferencesPage(
        preferences: _preferences!,
        permissions: NotificationPermissionActions(widget.permissionPort),
        onThemeChanged: (value) => setState(() => _themePreference = value),
      ),
    ));
  }

  NotificationCenterController? _notificationControllerFor(Person principal) {
    if (!principal.canReadNotifications ||
        _session == null ||
        _notificationCache == null) {
      return null;
    }
    final existing = _notificationController;
    if (existing != null && existing.principal.id == principal.id) {
      return existing;
    }
    return _notificationController = NotificationCenterController(
      client: NotificationApi(_session!),
      cache: _notificationCache!,
      principal: principal,
      onTerminalSession: _handleNotificationTerminalSession,
    );
  }

  Future<void> Function(Person) _profileUpdateCallback() {
    final epoch = _authEpoch;
    return (refreshed) => _applyProfileMutation(refreshed, epoch);
  }

  Future<void> _applyProfileMutation(Person refreshed, int epoch) async {
    final current = person;
    if (epoch != _authEpoch ||
        state != AuthViewState.authenticated ||
        current == null ||
        current.id != refreshed.id ||
        !mounted) {
      return;
    }
    // Reconcile the root projection and its principal-scoped cache together.
    await reconcileFreshReportPrincipal(
      cache: _reportCache!,
      previous: current,
      current: refreshed,
    );
    if (!_profileContextMatches(epoch, current.id)) return;
    await _notificationCache!.reconcileFreshPrincipal(current, refreshed);
    if (!_profileContextMatches(epoch, current.id)) return;
    final capabilityChanged = current.accessLevel != refreshed.accessLevel ||
        current.capabilities.length != refreshed.capabilities.length ||
        current.capabilities
            .any((capability) => !refreshed.capabilities.contains(capability));
    if (!refreshed.canReadNotifications || capabilityChanged) {
      await _api!.clearPendingProfileIntents();
      if (!_profileContextMatches(epoch, current.id)) return;
      await _notificationController?.invalidate();
      _notificationController = null;
      if (!_profileContextMatches(epoch, current.id)) return;
    }
    final committed = await _cache!.saveFenced(
      refreshed,
      games,
      lastSyncedAt!,
      generation: epoch,
      isCurrent: () => _profileContextMatches(epoch, current.id),
    );
    if (!committed) return;
    if (!mounted ||
        epoch != _authEpoch ||
        state != AuthViewState.authenticated ||
        person?.id != refreshed.id) {
      return;
    }
    setState(() => person = refreshed);
  }

  bool _profileContextMatches(int epoch, String personId) =>
      mounted &&
      AuthOperationContext(epoch, personId).matches(
        currentEpoch: _authEpoch,
        currentPersonId: person?.id,
      ) &&
      state == AuthViewState.authenticated &&
      person?.id == personId;

  void _handleNotificationTerminalSession() {
    _authEpoch++;
    _retirePendingReview();
    _navigatorKey.currentState?.popUntil((route) => route.isFirst);
    _showFailure(const SessionExpiredException());
  }

  Future<void> _handleProfileTerminalSession() =>
      _showFailure(const SessionExpiredException());
}

class LoginActionButton extends StatelessWidget {
  const LoginActionButton({
    super.key,
    required this.state,
    required this.onLogin,
    this.onGoogleLogin,
  });
  final AuthViewState state;
  final VoidCallback? onLogin;
  final VoidCallback? onGoogleLogin;

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
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        FloatingActionButton.extended(
          heroTag: 'google-login',
          onPressed: onGoogleLogin,
          label: const Text('Google 登入'),
          icon: const Icon(Icons.login),
        ),
        const SizedBox(height: 12),
        FloatingActionButton(
          heroTag: 'line-login',
          onPressed: onLogin,
          tooltip: 'LINE 登入',
          child: const Icon(Icons.login),
        ),
      ],
    );
  }
}

class DisplayNamePage extends StatefulWidget {
  const DisplayNamePage({
    super.key,
    required this.api,
    required this.person,
    this.onUpdated,
    this.onTerminalSession,
  });
  final BasicApi api;
  final Person person;
  final Future<void> Function(Person person)? onUpdated;
  final Future<void> Function()? onTerminalSession;
  @override
  State<DisplayNamePage> createState() => _DisplayNamePageState();
}

class _DisplayNamePageState extends State<DisplayNamePage> {
  late final TextEditingController _name =
      TextEditingController(text: widget.person.displayName);
  bool _saving = false;
  String? _message;
  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final value = _name.text.trim();
    if (value.isEmpty || value.length > 120) {
      setState(() => _message = '顯示名稱必須為 1 到 120 個字元。');
      return;
    }
    setState(() {
      _saving = true;
      _message = null;
    });
    try {
      final result = await widget.api.updateDisplayName(
        value,
        personId: widget.person.id,
      );
      await widget.onUpdated?.call(result.person);
      if (mounted) Navigator.of(context).pop();
    } on ProfileMutationUncertainException {
      if (mounted) setState(() => _message = '結果尚未確認；請使用相同名稱重試。');
    } on SessionExpiredException {
      await widget.onTerminalSession?.call();
    } on ApiError catch (error) {
      if (error.code == ApiErrorCode.unauthenticated ||
          error.code == ApiErrorCode.sessionExpired) {
        await widget.onTerminalSession?.call();
      } else if (mounted) {
        setState(() => _message = '無法更新顯示名稱，請稍後重試。');
      }
    } on Object {
      if (mounted) setState(() => _message = '無法更新顯示名稱，請稍後重試。');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('編輯顯示名稱')),
        body: Padding(
          padding: const EdgeInsets.all(AppSpacing.regular),
          child: Column(children: [
            TextField(
                controller: _name,
                maxLength: 120,
                autofocus: true,
                decoration: const InputDecoration(labelText: '顯示名稱')),
            if (_message != null) Text(_message!),
            const SizedBox(height: AppSpacing.regular),
            FilledButton(
                onPressed: _saving ? null : _save,
                child: Text(_saving ? '儲存中…' : '儲存')),
          ]),
        ),
      );
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
    this.publishingClient,
    this.notificationController,
    this.onRefresh,
    this.onPersonUpdated,
    this.onProfileTerminalSession,
    this.onOpenSettings,
    this.identityLink,
    this.platform,
    this.diagnosticEnabled = true,
  });
  final BasicApi api;
  final Person person;
  final List<Game> games;
  final bool online;
  final DateTime lastSyncedAt;
  final PrincipalProvenance? principalProvenance;
  final PrincipalOfficerReportCache? reportCache;
  final NotificationPublishingClient? publishingClient;
  final NotificationCenterController? notificationController;
  final Future<bool> Function()? onRefresh;
  final Future<void> Function(Person person)? onPersonUpdated;
  final Future<void> Function()? onProfileTerminalSession;
  final VoidCallback? onOpenSettings;
  final IdentityLinkController? identityLink;
  final String? platform;

  /// Test injection can disable the diagnostic, but cannot enable it in a
  /// release build because rendering is always additionally gated by
  /// [kDebugMode].
  final bool diagnosticEnabled;

  @override
  State<BasicGamesView> createState() => _BasicGamesViewState();
}

class _BasicGamesViewState extends State<BasicGamesView> {
  final _scrollController = ScrollController();
  bool _refreshInProgress = false;
  String? _refreshResult;

  Future<void> _refresh() async {
    final refresh = widget.onRefresh;
    if (!widget.online || refresh == null || _refreshInProgress) return;
    setState(() {
      _refreshInProgress = true;
      _refreshResult = null;
    });
    try {
      final succeeded = await refresh();
      if (!mounted) return;
      if (succeeded) {
        await _scrollController.animateTo(
          0,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
        );
        if (!mounted) return;
        setState(() => _refreshResult = '重新整理完成，已回到賽事列表開頭');
      } else {
        setState(() => _refreshResult = '重新整理失敗，仍顯示上次成功同步資料');
      }
    } on Object {
      if (mounted) {
        setState(() => _refreshResult = '重新整理失敗，仍顯示上次成功同步資料');
      }
    } finally {
      if (mounted) setState(() => _refreshInProgress = false);
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
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
      child: ListView(
        controller: _scrollController,
        padding: const EdgeInsets.all(AppSpacing.regular),
        children: [
          if (!widget.online)
            Semantics(
              key: const ValueKey('offline-read-only'),
              label: '離線唯讀，出席回覆已停用',
              child: const AppStatusPanel(
                icon: Icons.cloud_off,
                title: '離線唯讀模式',
                message: '目前顯示上次成功同步的資料，無法重新整理或回覆出席。',
              ),
            ),
          AppSurfaceCard(
            child: Semantics(
              key: const ValueKey('games-last-sync'),
              label:
                  '最後成功同步：${localizations.formatFullDate(widget.lastSyncedAt.toLocal())} ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(widget.lastSyncedAt.toLocal()))}',
              child: ListTile(
                title: Text(widget.person.displayName),
                subtitle: Text(
                  '最後同步：${localizations.formatFullDate(widget.lastSyncedAt.toLocal())} ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(widget.lastSyncedAt.toLocal()))}',
                ),
                trailing: IconButton(
                  key: const ValueKey('games-refresh'),
                  tooltip: '重新整理賽事',
                  onPressed: widget.online &&
                          widget.onRefresh != null &&
                          !_refreshInProgress
                      ? _refresh
                      : null,
                  icon: _refreshInProgress
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.refresh),
                ),
              ),
            ),
          ),
          if (_refreshInProgress || _refreshResult != null)
            Semantics(
              key: const ValueKey('games-refresh-result'),
              label: _refreshInProgress ? '正在重新整理賽事' : _refreshResult,
              liveRegion: true,
              child: ExcludeSemantics(
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    vertical: AppSpacing.compact,
                  ),
                  child: Row(
                    children: [
                      if (_refreshInProgress)
                        const SizedBox(
                          key: ValueKey('games-refresh-progress'),
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      else
                        Icon(
                          _refreshResult!.startsWith('重新整理完成')
                              ? Icons.check_circle_outline
                              : Icons.error_outline,
                        ),
                      const SizedBox(width: AppSpacing.compact),
                      Expanded(
                        child: Text(
                          _refreshInProgress ? '正在重新整理賽事…' : _refreshResult!,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          AppSurfaceCard(
            child: ListTile(
              key: const ValueKey('account-data-status-entry'),
              leading: const Icon(Icons.account_circle_outlined),
              title: const Text('帳號與資料狀態'),
              subtitle: const Text('查看目前顯示的帳號與資料來源'),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => AccountDataStatusPage(
                    person: widget.person,
                    lastSyncedAt: widget.lastSyncedAt,
                    provenance: widget.principalProvenance,
                    identityLink: widget.online ? widget.identityLink : null,
                    platform: widget.platform,
                  ),
                ),
              ),
            ),
          ),
          if (widget.onOpenSettings != null)
            AppSurfaceCard(
              child: ListTile(
                key: const ValueKey('local-preferences-entry'),
                leading: const Icon(Icons.settings_outlined),
                title: const Text('App 偏好設定'),
                subtitle: const Text('主題、通知權限與系統設定'),
                onTap: widget.onOpenSettings,
              ),
            ),
          if (widget.online)
            AppSurfaceCard(
              child: ListTile(
                key: const ValueKey('edit-display-name-entry'),
                leading: const Icon(Icons.edit_outlined),
                title: const Text('編輯顯示名稱'),
                subtitle: const Text('只會更新目前登入帳號的顯示名稱'),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => DisplayNamePage(
                      api: widget.api,
                      person: widget.person,
                      onUpdated: widget.onPersonUpdated,
                      onTerminalSession: widget.onProfileTerminalSession,
                    ),
                  ),
                ),
              ),
            ),
          AppSurfaceCard(
            child: ListTile(
              key: const ValueKey('support-app-info-entry'),
              leading: const Icon(Icons.support_agent_outlined),
              title: const Text('支援與 App 資訊'),
              subtitle: const Text('帳號協助、資料使用與版本資訊'),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const SupportAppInfoPage(),
                ),
              ),
            ),
          ),
          if (DebugPrincipalProjection.shouldRender(
            debugBuild: kDebugMode,
            diagnosticEnabled: widget.diagnosticEnabled,
          ))
            DebugPrincipalProjection(
              person: widget.person,
              provenance: widget.principalProvenance,
            ),
          if (widget.person.canReadNotifications &&
              widget.notificationController != null)
            AnimatedBuilder(
              animation: widget.notificationController!,
              builder: (context, _) => AppSurfaceCard(
                child: ListTile(
                  key: const ValueKey('notification-center-entry'),
                  leading: const Icon(Icons.notifications_outlined),
                  title: const Text('通知中心'),
                  subtitle: Text(
                    widget.notificationController!.unreadCount == 0
                        ? '查看隊務通知'
                        : '${widget.notificationController!.unreadCount} 則未讀通知',
                  ),
                  trailing: widget.notificationController!.unreadCount == 0
                      ? null
                      : Badge(
                          label: Text(
                            '${widget.notificationController!.unreadCount}',
                          ),
                        ),
                  onTap: () {
                    final controller = widget.notificationController!;
                    Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => NotificationCenter(
                          controller: controller,
                          online: widget.online,
                          onOpen: _openNotificationDestination,
                        ),
                      ),
                    );
                    controller.load(online: widget.online);
                  },
                ),
              ),
            ),
          if (widget.person.canReadAttendanceReport)
            AppSurfaceCard(
              child: ListTile(
                key: const ValueKey('management-report-entry'),
                leading: const Icon(Icons.assessment_outlined),
                title: const Text('出席報表'),
                subtitle: const Text('Officer／Admin 唯讀'),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => CanonicalManagementReportsPage(
                      api: widget.api,
                      person: widget.person,
                      games: widget.games,
                      online: widget.online,
                      cache: widget.reportCache,
                    ),
                  ),
                ),
              ),
            ),
          if (widget.online && widget.person.canPublishNotifications)
            AppSurfaceCard(
              child: ListTile(
                key: const ValueKey('notification-publishing-entry'),
                leading: const Icon(Icons.campaign_outlined),
                title: const Text('發布隊務通知'),
                subtitle: const Text('先預覽收件人，再輸入確認文字發布'),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => OfficerNotificationPublishingPage(
                      client: widget.publishingClient ??
                          OfficerNotificationPublisher(
                            widget.api.session,
                            widget.person,
                          ),
                      games: widget.games,
                    ),
                  ),
                ),
              ),
            ),
          if (widget.person.canReadEvents)
            AppSurfaceCard(
              child: ListTile(
                key: const ValueKey('events-entry'),
                leading: const Icon(Icons.event_note_outlined),
                title: const Text('活動行程'),
                subtitle: Text(widget.online ? '查看受邀活動與行程' : '離線時無法載入活動'),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => EventListPage(
                      api: widget.api,
                      online: widget.online,
                      principalScope: widget.person.id,
                      visibleGames: widget.games,
                      onTerminalSession: widget.onProfileTerminalSession,
                    ),
                  ),
                ),
              ),
            ),
          AppSurfaceCard(
            child: ListTile(
              key: const ValueKey('schedule-discovery-entry'),
              leading: const Icon(Icons.calendar_month_outlined),
              title: const Text('賽程探索'),
              subtitle:
                  Text(widget.online ? '依日期、球隊或場地尋找已載入賽事' : '離線唯讀・可能不是最新賽程'),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => ScheduleDiscoveryPage(
                    api: widget.api,
                    games: widget.games,
                    online: widget.online,
                  ),
                ),
              ),
            ),
          ),
          if (orderedGames.isEmpty)
            Semantics(
              key: const ValueKey('games-empty'),
              label: '目前沒有可顯示的賽事',
              child: const AppStatusPanel(
                icon: Icons.event_busy,
                title: '目前沒有賽事',
                message: '有新賽事時會顯示在這裡。',
              ),
            ),
          MemberActionHome(
            api: widget.api,
            principalScope: widget.person.id,
            games: orderedGames,
            online: widget.online,
            onOpenGame: (game) async => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => widget.online
                    ? GameDetailPage(api: widget.api, gameId: game.id)
                    : CachedGameDetailPage(game: game),
              ),
            ),
            onOpenSchedule: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => ScheduleDiscoveryPage(
                    api: widget.api,
                    games: widget.games,
                    online: widget.online),
              ),
            ),
          ),
          if (orderedGames.isNotEmpty)
            NextAuthorizedGameCard(
              api: widget.api,
              game: orderedGames.first,
              online: widget.online,
              onOpen: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => widget.online
                    ? GameDetailPage(
                        api: widget.api, gameId: orderedGames.first.id)
                    : CachedGameDetailPage(game: orderedGames.first),
              )),
            ),
          for (final game in orderedGames.skip(1))
            AppSurfaceCard(
              child: ListTile(
                key: ValueKey('game-${game.id}'),
                title: Text(
                  '${game.homeTeam ?? '主隊'} vs ${game.awayTeam ?? '客隊'}',
                ),
                subtitle: Text(_formatGameMetadata(localizations, game)),
                trailing: const Icon(Icons.chevron_right),
                onTap: widget.online
                    ? () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => GameDetailPage(
                                api: widget.api, gameId: game.id),
                          ),
                        )
                    : null,
              ),
            ),
        ],
      ),
    );
    final scrollableGamesView = ScrollConfiguration(
      behavior: ScrollConfiguration.of(context)
          .copyWith(physics: const AlwaysScrollableScrollPhysics()),
      child: content,
    );
    if (!widget.online || widget.onRefresh == null) return scrollableGamesView;
    return RefreshIndicator(
      key: const ValueKey('games-pull-refresh'),
      semanticsLabel: '下拉重新整理賽事',
      onRefresh: _refresh,
      child: scrollableGamesView,
    );
  }

  void _openNotificationDestination(MobileNotification item) {
    switch (item.destination.type) {
      case NotificationDestinationType.notification:
        Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => NotificationDetailPage(notification: item),
          ),
        );
      case NotificationDestinationType.game:
        Game? game;
        for (final candidate in widget.games) {
          if (candidate.id == item.destination.id) {
            game = candidate;
            break;
          }
        }
        if (game == null) {
          _showDestinationFeedback('找不到可查看的賽事，仍停留在通知中心。');
          return;
        }
        Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => widget.online
                ? GameDetailPage(api: widget.api, gameId: game!.id)
                : CachedGameDetailPage(game: game!),
          ),
        );
      case NotificationDestinationType.notificationList:
        _showDestinationFeedback('此通知沒有可開啟的內容，仍停留在通知中心。');
    }
  }

  void _showDestinationFeedback(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

enum SchedulePresentationFilter { all, withLocation, withoutLocation }

enum SchedulePresentation { month, week, agenda }

class ScheduleCalendarProjection {
  static DateTime dateOnly(DateTime value) =>
      DateTime(value.year, value.month, value.day);

  static DateTime localGameDay(Game game) => dateOnly(game.startAt.toLocal());

  static DateTime weekStart(DateTime day) {
    final localDay = dateOnly(day);
    return localDay.subtract(Duration(days: localDay.weekday - 1));
  }

  static List<DateTime> weekDays(DateTime day) {
    final start = weekStart(day);
    return List.generate(7, (index) => start.add(Duration(days: index)));
  }

  static List<DateTime> monthGrid(DateTime month) {
    final first = DateTime(month.year, month.month);
    final start = weekStart(first);
    return List.generate(42, (index) => start.add(Duration(days: index)));
  }

  static Map<DateTime, List<Game>> groupByLocalDay(Iterable<Game> games) {
    final groups = <DateTime, List<Game>>{};
    for (final game in games) {
      groups.putIfAbsent(localGameDay(game), () => []).add(game);
    }
    for (final values in groups.values) {
      values.sort((left, right) => left.startAt.compareTo(right.startAt));
    }
    return groups;
  }
}

class EventListPage extends StatefulWidget {
  const EventListPage({
    super.key,
    required this.api,
    required this.online,
    required this.principalScope,
    required this.visibleGames,
    this.onTerminalSession,
  });

  final BasicApi api;
  final bool online;
  final String principalScope;
  final List<Game> visibleGames;
  final Future<void> Function()? onTerminalSession;

  @override
  State<EventListPage> createState() => _EventListPageState();
}

class _EventListPageState extends State<EventListPage> {
  List<TeamEvent>? _events;
  Object? _error;

  @override
  void initState() {
    super.initState();
    if (widget.online) _load();
  }

  @override
  void didUpdateWidget(covariant EventListPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.principalScope != widget.principalScope ||
        !identical(oldWidget.api, widget.api) ||
        oldWidget.online != widget.online) {
      if (widget.online) {
        _load();
      } else {
        setState(() {
          _events = null;
          _error = null;
        });
      }
    }
  }

  bool _matches(AuthOperationContext operation) =>
      mounted &&
      operation.matches(
        currentEpoch: widget.api.session.generation,
        currentPersonId: widget.principalScope,
      );

  bool _samePrincipal(AuthOperationContext operation) =>
      mounted &&
      operation.personId == widget.principalScope &&
      (widget.api.session.generation == operation.epoch ||
          widget.api.session.generation == operation.epoch + 1);

  Future<void> _load() async {
    final operation = AuthOperationContext(
      widget.api.session.generation,
      widget.principalScope,
    );
    setState(() {
      _events = null;
      _error = null;
    });
    try {
      final events = await widget.api.events();
      if (!_matches(operation)) return;
      setState(() => _events = events);
    } on Object catch (error) {
      if (isTerminalSessionFailure(error)) {
        if (_samePrincipal(operation)) await widget.onTerminalSession?.call();
      } else if (_matches(operation)) {
        setState(() => _error = error);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('活動行程')),
        body: !widget.online
            ? const Padding(
                padding: EdgeInsets.all(AppSpacing.regular),
                child: AppStatusPanel(
                  key: ValueKey('events-offline-unavailable'),
                  icon: Icons.cloud_off,
                  title: '離線無法查看活動',
                  message: '活動不會儲存在此裝置；連線後再試一次。',
                ),
              )
            : _error != null
                ? Padding(
                    padding: const EdgeInsets.all(AppSpacing.regular),
                    child: Column(
                      children: [
                        const AppStatusPanel(
                          key: ValueKey('events-error'),
                          icon: Icons.error_outline,
                          title: '無法載入活動',
                          message: '請確認網路連線後再試一次。',
                        ),
                        const SizedBox(height: AppSpacing.regular),
                        FilledButton(
                          key: const ValueKey('events-retry'),
                          onPressed: _load,
                          child: const Text('重試'),
                        ),
                      ],
                    ),
                  )
                : _events == null
                    ? const Center(
                        child: CircularProgressIndicator(
                          key: ValueKey('events-loading'),
                        ),
                      )
                    : _events!.isEmpty
                        ? const Padding(
                            padding: EdgeInsets.all(AppSpacing.regular),
                            child: AppStatusPanel(
                              key: ValueKey('events-empty'),
                              icon: Icons.event_available_outlined,
                              title: '目前沒有活動',
                              message: '受邀且已發布的活動會顯示在這裡。',
                            ),
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.all(AppSpacing.regular),
                            itemCount: _events!.length,
                            itemBuilder: (context, index) {
                              final event = _events![index];
                              return AppSurfaceCard(
                                child: ListTile(
                                  key: ValueKey('event-${event.id}'),
                                  leading: Icon(event.cancelled
                                      ? Icons.event_busy
                                      : Icons.event_available),
                                  title: Text(event.title),
                                  subtitle:
                                      Text(_eventMetadata(context, event)),
                                  trailing: const Icon(Icons.chevron_right),
                                  onTap: () => Navigator.of(context).push(
                                    MaterialPageRoute<void>(
                                      builder: (_) => EventDetailPage(
                                        api: widget.api,
                                        eventId: event.id,
                                        principalScope: widget.principalScope,
                                        visibleGames: widget.visibleGames,
                                        onTerminalSession:
                                            widget.onTerminalSession,
                                      ),
                                    ),
                                  ),
                                ),
                              );
                            },
                          ),
      );
}

class EventDetailPage extends StatefulWidget {
  const EventDetailPage({
    super.key,
    required this.api,
    required this.eventId,
    required this.principalScope,
    required this.visibleGames,
    this.onTerminalSession,
  });

  final BasicApi api;
  final String eventId;
  final String principalScope;
  final List<Game> visibleGames;
  final Future<void> Function()? onTerminalSession;

  @override
  State<EventDetailPage> createState() => _EventDetailPageState();
}

class _EventDetailPageState extends State<EventDetailPage> {
  TeamEvent? _event;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant EventDetailPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.principalScope != widget.principalScope ||
        oldWidget.eventId != widget.eventId ||
        !identical(oldWidget.api, widget.api)) {
      _load();
    }
  }

  bool _matches(AuthOperationContext operation) =>
      mounted &&
      operation.matches(
        currentEpoch: widget.api.session.generation,
        currentPersonId: widget.principalScope,
      );

  bool _samePrincipal(AuthOperationContext operation) =>
      mounted &&
      operation.personId == widget.principalScope &&
      (widget.api.session.generation == operation.epoch ||
          widget.api.session.generation == operation.epoch + 1);

  Future<void> _load() async {
    final operation = AuthOperationContext(
      widget.api.session.generation,
      widget.principalScope,
    );
    setState(() {
      _event = null;
      _error = null;
    });
    try {
      final event = await widget.api.event(widget.eventId);
      if (!_matches(operation)) return;
      setState(() => _event = event);
    } on Object catch (error) {
      if (isTerminalSessionFailure(error)) {
        if (_samePrincipal(operation)) await widget.onTerminalSession?.call();
      } else if (_matches(operation)) {
        setState(() => _error = error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final event = _event;
    return Scaffold(
      appBar: AppBar(title: const Text('活動詳情')),
      body: _error != null
          ? Padding(
              padding: const EdgeInsets.all(AppSpacing.regular),
              child: Column(
                children: [
                  const AppStatusPanel(
                    key: ValueKey('event-detail-error'),
                    icon: Icons.error_outline,
                    title: '無法載入活動詳情',
                    message: '請確認網路連線後再試一次。',
                  ),
                  const SizedBox(height: AppSpacing.regular),
                  FilledButton(onPressed: _load, child: const Text('重試')),
                ],
              ),
            )
          : event == null
              ? const Center(
                  child: CircularProgressIndicator(
                    key: ValueKey('event-detail-loading'),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(AppSpacing.regular),
                  children: [
                    Text(event.title,
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: AppSpacing.compact),
                    Text(_eventMetadata(context, event)),
                    if (event.cancelled) ...[
                      const SizedBox(height: AppSpacing.regular),
                      const AppStatusPanel(
                        key: ValueKey('event-cancelled'),
                        icon: Icons.event_busy,
                        title: '活動已取消',
                        message: '此活動與行程僅供查看。',
                      ),
                    ],
                    const SizedBox(height: AppSpacing.regular),
                    Text('行程', style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: AppSpacing.compact),
                    if (event.activities.isEmpty)
                      const AppStatusPanel(
                        key: ValueKey('activities-empty'),
                        icon: Icons.schedule_outlined,
                        title: '尚無行程',
                        message: '此活動目前沒有可顯示的行程項目。',
                      ),
                    for (final activity in event.activities)
                      _activityTile(context, activity),
                  ],
                ),
    );
  }

  Widget _activityTile(BuildContext context, EventActivity activity) {
    final game = visibleLinkedGame(activity.linkedGameId, widget.visibleGames);
    return AppSurfaceCard(
      child: ListTile(
        key: ValueKey('activity-${activity.id}'),
        leading: const Icon(Icons.timeline),
        title: Text(activity.title),
        subtitle: Text(_activityMetadata(context, activity)),
        trailing: game == null ? null : const Icon(Icons.sports_basketball),
        onTap: game == null
            ? null
            : () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => GameDetailPage(
                      api: widget.api,
                      gameId: game.id,
                    ),
                  ),
                ),
      ),
    );
  }
}

Game? visibleLinkedGame(String? linkedGameId, Iterable<Game> visibleGames) {
  if (linkedGameId == null) return null;
  for (final game in visibleGames) {
    if (game.id == linkedGameId) return game;
  }
  return null;
}

String _eventMetadata(BuildContext context, TeamEvent event) {
  final localizations = MaterialLocalizations.of(context);
  final localStart = event.startAt.toLocal();
  final localEnd = event.endAt?.toLocal();
  final status = event.cancelled ? '已取消' : '已發布';
  final start =
      localizations.formatTimeOfDay(TimeOfDay.fromDateTime(localStart));
  final end = localEnd == null
      ? ''
      : '–${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(localEnd))}';
  return '$status・${localizations.formatFullDate(localStart)} $start$end';
}

String _activityMetadata(BuildContext context, EventActivity activity) {
  final localizations = MaterialLocalizations.of(context);
  final start = activity.startAt.toLocal();
  final end = activity.endAt?.toLocal();
  final endLabel = end == null
      ? ''
      : '–${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(end))}';
  return '${localizations.formatFullDate(start)} '
      '${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(start))}$endLabel';
}

class ScheduleDiscoveryPage extends StatefulWidget {
  const ScheduleDiscoveryPage({
    super.key,
    required this.api,
    required this.games,
    required this.online,
  });

  final BasicApi api;
  final List<Game> games;
  final bool online;

  @override
  State<ScheduleDiscoveryPage> createState() => _ScheduleDiscoveryPageState();
}

class _ScheduleDiscoveryPageState extends State<ScheduleDiscoveryPage> {
  final _searchController = TextEditingController();
  final _scrollController = ScrollController();
  SchedulePresentationFilter _filter = SchedulePresentationFilter.all;
  SchedulePresentation _presentation = SchedulePresentation.agenda;
  String _query = '';
  late DateTime _selectedDay;

  @override
  void initState() {
    super.initState();
    _selectedDay = widget.games.isEmpty
        ? ScheduleCalendarProjection.dateOnly(DateTime.now())
        : ScheduleCalendarProjection.localGameDay(
            (List<Game>.of(widget.games)
                  ..sort(
                      (left, right) => left.startAt.compareTo(right.startAt)))
                .first,
          );
  }

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  List<Game> get _visibleGames {
    final query = _query.trim().toLowerCase();
    final games = widget.games.where((game) {
      if (_filter == SchedulePresentationFilter.withLocation &&
          (game.location == null || game.location!.trim().isEmpty)) {
        return false;
      }
      if (_filter == SchedulePresentationFilter.withoutLocation &&
          game.location != null &&
          game.location!.trim().isNotEmpty) {
        return false;
      }
      if (query.isEmpty) return true;
      return [game.homeTeam, game.awayTeam, game.location]
          .whereType<String>()
          .any((value) => value.toLowerCase().contains(query));
    }).toList()
      ..sort((left, right) => left.startAt.compareTo(right.startAt));
    return games;
  }

  @override
  Widget build(BuildContext context) {
    final localizations = MaterialLocalizations.of(context);
    final games = _visibleGames;
    final groups = <DateTime, List<Game>>{};
    groups.addAll(ScheduleCalendarProjection.groupByLocalDay(games));
    return Scaffold(
      appBar: AppBar(title: const Text('賽程探索')),
      body: ListView(
        controller: _scrollController,
        padding: const EdgeInsets.all(AppSpacing.regular),
        children: [
          if (!widget.online)
            const AppStatusPanel(
              icon: Icons.cloud_off,
              title: '離線唯讀賽程',
              message: '僅顯示此帳號已載入的本機賽事，資料可能過期。',
            ),
          TextField(
            key: const ValueKey('schedule-search'),
            controller: _searchController,
            onChanged: (value) => setState(() => _query = value),
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              labelText: '搜尋球隊或場地',
            ),
          ),
          const SizedBox(height: AppSpacing.compact),
          Wrap(
            spacing: AppSpacing.compact,
            children: [
              for (final filter in SchedulePresentationFilter.values)
                ChoiceChip(
                  key: ValueKey('schedule-filter-${filter.name}'),
                  label: Text(_filterLabel(filter)),
                  selected: _filter == filter,
                  onSelected: (_) => setState(() => _filter = filter),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.regular),
          SegmentedButton<SchedulePresentation>(
            key: const ValueKey('schedule-presentation-switch'),
            segments: const [
              ButtonSegment(
                  value: SchedulePresentation.month, label: Text('月')),
              ButtonSegment(value: SchedulePresentation.week, label: Text('週')),
              ButtonSegment(
                  value: SchedulePresentation.agenda, label: Text('列表')),
            ],
            selected: {_presentation},
            onSelectionChanged: (selection) =>
                setState(() => _presentation = selection.single),
          ),
          const SizedBox(height: AppSpacing.compact),
          if (_presentation != SchedulePresentation.agenda)
            Row(
              children: [
                IconButton(
                  key: const ValueKey('schedule-previous-period'),
                  tooltip: '上一期間',
                  onPressed: () => setState(() => _movePeriod(-1)),
                  icon: const Icon(Icons.chevron_left),
                ),
                Expanded(
                  child: Text(
                    _periodLabel(localizations),
                    textAlign: TextAlign.center,
                    key: const ValueKey('schedule-period-label'),
                  ),
                ),
                TextButton(
                  key: const ValueKey('schedule-today'),
                  onPressed: () => setState(() {
                    _selectedDay =
                        ScheduleCalendarProjection.dateOnly(DateTime.now());
                  }),
                  child: const Text('今天'),
                ),
                IconButton(
                  key: const ValueKey('schedule-next-period'),
                  tooltip: '下一期間',
                  onPressed: () => setState(() => _movePeriod(1)),
                  icon: const Icon(Icons.chevron_right),
                ),
              ],
            ),
          ..._presentationContents(localizations, games, groups),
        ],
      ),
    );
  }

  List<Widget> _presentationContents(
    MaterialLocalizations localizations,
    List<Game> games,
    Map<DateTime, List<Game>> groups,
  ) {
    final allGroups = ScheduleCalendarProjection.groupByLocalDay(widget.games);
    if (widget.games.isEmpty) {
      return const [
        AppStatusPanel(
          key: ValueKey('schedule-empty'),
          icon: Icons.event_busy,
          title: '目前沒有賽事',
          message: '有新賽事時會顯示在這裡。',
        ),
      ];
    }
    if (_presentation == SchedulePresentation.agenda) {
      if (games.isEmpty) return [_noMatchPanel()];
      return [
        for (final entry in groups.entries)
          ..._daySection(localizations, entry.key, entry.value)
      ];
    }
    if (_presentation == SchedulePresentation.week) {
      return [
        for (final day in ScheduleCalendarProjection.weekDays(_selectedDay))
          ..._daySection(
            localizations,
            day,
            groups[day] ?? const [],
            compactEmpty: true,
            emptyState:
                allGroups[day]?.isNotEmpty ?? false ? 'no-match' : 'no-games',
          ),
      ];
    }
    return [
      GridView.count(
        key: const ValueKey('schedule-month-grid'),
        crossAxisCount: 7,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        children: [
          for (final day in ScheduleCalendarProjection.monthGrid(_selectedDay))
            Semantics(
              selected: day == _selectedDay,
              label:
                  '${localizations.formatFullDate(day)}，${groups[day]?.length ?? 0} 場符合賽事',
              child: TextButton(
                key: ValueKey('schedule-day-${_dayToken(day)}'),
                style: TextButton.styleFrom(
                  backgroundColor: day == _selectedDay
                      ? Theme.of(context).colorScheme.secondaryContainer
                      : null,
                  foregroundColor: day == _selectedDay
                      ? Theme.of(context).colorScheme.onSecondaryContainer
                      : null,
                  side: day == _selectedDay
                      ? BorderSide(
                          color: Theme.of(context).colorScheme.primary,
                          width: 2,
                        )
                      : null,
                ),
                onPressed: () => setState(() => _selectedDay = day),
                child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text('${day.day}'),
                      if ((groups[day]?.isNotEmpty ?? false))
                        Text('${groups[day]!.length} 場'),
                    ]),
              ),
            ),
        ],
      ),
      if (!(allGroups[_selectedDay]?.isNotEmpty ?? false))
        const AppStatusPanel(
          key: ValueKey('schedule-day-no-games'),
          icon: Icons.event_busy,
          title: '這一天沒有賽事',
          message: '請選擇其他日期。',
        )
      else if (!(groups[_selectedDay]?.isNotEmpty ?? false))
        _noMatchPanel(key: const ValueKey('schedule-day-no-match'))
      else
        ..._daySection(localizations, _selectedDay, groups[_selectedDay]!),
    ];
  }

  List<Widget> _daySection(
    MaterialLocalizations localizations,
    DateTime day,
    List<Game> games, {
    bool compactEmpty = false,
    String emptyState = 'no-match',
  }) =>
      [
        Semantics(
          header: true,
          child: Padding(
            padding: const EdgeInsets.only(top: AppSpacing.compact),
            child: Text(
              localizations.formatFullDate(day),
              key: ValueKey('schedule-date-${day.toIso8601String()}'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ),
        if (games.isEmpty && compactEmpty)
          Padding(
            key: ValueKey('schedule-week-${_dayToken(day)}-$emptyState'),
            padding: const EdgeInsets.only(bottom: AppSpacing.compact),
            child: Text(emptyState == 'no-games' ? '沒有賽事' : '沒有符合賽事'),
          ),
        for (final game in games) _gameTile(localizations, game),
      ];

  Widget _gameTile(MaterialLocalizations localizations, Game game) =>
      AppSurfaceCard(
        child: ListTile(
          key: ValueKey('schedule-game-${game.id}'),
          title: Text('${game.homeTeam ?? '主隊'} vs ${game.awayTeam ?? '客隊'}'),
          subtitle: Text(_formatGameMetadata(localizations, game)),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => widget.online
                  ? GameDetailPage(api: widget.api, gameId: game.id)
                  : CachedGameDetailPage(game: game),
            ),
          ),
        ),
      );

  AppStatusPanel _noMatchPanel({Key? key}) => AppStatusPanel(
        key: key ?? const ValueKey('schedule-no-match'),
        icon: Icons.manage_search_outlined,
        title: '找不到符合的賽事',
        message: '請調整搜尋文字或篩選條件。',
      );

  void _movePeriod(int delta) {
    _selectedDay = switch (_presentation) {
      SchedulePresentation.month =>
        DateTime(_selectedDay.year, _selectedDay.month + delta, 1),
      SchedulePresentation.week => _selectedDay.add(Duration(days: 7 * delta)),
      SchedulePresentation.agenda => DateTime(
          _selectedDay.year, _selectedDay.month + delta, _selectedDay.day),
    };
  }

  String _periodLabel(MaterialLocalizations localizations) =>
      switch (_presentation) {
        SchedulePresentation.month =>
          '${_selectedDay.year} 年 ${_selectedDay.month} 月',
        SchedulePresentation.week =>
          '${localizations.formatShortDate(ScheduleCalendarProjection.weekStart(_selectedDay))} – ${localizations.formatShortDate(ScheduleCalendarProjection.weekDays(_selectedDay).last)}',
        SchedulePresentation.agenda => '依日期排列',
      };

  String _dayToken(DateTime day) =>
      '${day.year.toString().padLeft(4, '0')}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}';

  String _filterLabel(SchedulePresentationFilter filter) {
    switch (filter) {
      case SchedulePresentationFilter.all:
        return '全部';
      case SchedulePresentationFilter.withLocation:
        return '有場地';
      case SchedulePresentationFilter.withoutLocation:
        return '未定場地';
    }
  }
}

class MemberActionHome extends StatefulWidget {
  const MemberActionHome(
      {super.key,
      required this.api,
      required this.principalScope,
      required this.games,
      required this.online,
      required this.onOpenGame,
      required this.onOpenSchedule,
      this.controller});
  final BasicApi api;
  final String principalScope;
  final List<Game> games;
  final bool online;
  final Future<void> Function(Game) onOpenGame;
  final VoidCallback onOpenSchedule;
  final MemberActionController? controller;
  @override
  State<MemberActionHome> createState() => _MemberActionHomeState();
}

class _MemberActionHomeState extends State<MemberActionHome> {
  late final MemberActionController _controller;
  late final bool _ownsController;
  @override
  void initState() {
    super.initState();
    _ownsController = widget.controller == null;
    _controller =
        widget.controller ?? MemberActionController(widget.api.attendance);
    _controller.load(
      principalScope: widget.principalScope,
      games: widget.games,
      online: widget.online,
    );
  }

  @override
  void didUpdateWidget(covariant MemberActionHome oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.games != widget.games ||
        oldWidget.online != widget.online ||
        oldWidget.principalScope != widget.principalScope) {
      _controller.load(
        principalScope: widget.principalScope,
        games: widget.games,
        online: widget.online,
      );
    }
  }

  @override
  void dispose() {
    if (_ownsController) _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: _controller,
        builder: (context, _) => AppSurfaceCard(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('行動首頁'),
            Text('僅評估已載入未來最多 5 場：已確認待處理 ${_controller.pending.length} 場'),
            Text(_controller.message(online: widget.online),
                key: ValueKey('action-home-${_controller.state.name}')),
            if (_controller.nearestAction case final game?)
              TextButton(
                  key: const ValueKey('action-home-open-nearest'),
                  onPressed: () async {
                    await widget.onOpenGame(game);
                    await _controller.refreshGame(game, online: widget.online);
                  },
                  child: const Text('查看並回覆')),
            if (_controller.state == MemberActionState.retryableError)
              TextButton(
                key: const ValueKey('action-home-retry'),
                onPressed: () => _controller.load(
                  principalScope: widget.principalScope,
                  games: widget.games,
                  online: widget.online,
                ),
                child: const Text('重試確認'),
              ),
            TextButton(
                key: const ValueKey('action-home-schedule'),
                onPressed: widget.onOpenSchedule,
                child: const Text('完整賽程')),
          ]),
        ),
      );
}

enum MemberActionState {
  loading,
  actionable,
  resolved,
  partialUnknown,
  empty,
  retryableError
}

class MemberActionController extends ChangeNotifier {
  MemberActionController(this._read, {DateTime Function()? clock})
      : _clock = clock ?? DateTime.now;
  final Future<AttendanceSnapshot> Function(String) _read;
  final DateTime Function() _clock;
  final Map<String, AttendanceReply?> _known = {};
  final Map<String, Future<void>> _inFlight = {};
  String? _principalScope;
  String? _contextKey;
  int _generation = 0;
  List<Game> window = const [];
  MemberActionState state = MemberActionState.loading;
  List<Game> get pending => window
      .where((game) =>
          _known.containsKey(game.id) &&
          (_known[game.id] == null ||
              _known[game.id] == AttendanceReply.undecided))
      .toList();
  List<Game> get unknown =>
      window.where((game) => !_known.containsKey(game.id)).toList();
  Game? get nearestAction => pending.isEmpty ? null : pending.first;
  static List<Game> selectWindow(List<Game> games, DateTime now) =>
      (List<Game>.of(games)..sort((a, b) => a.startAt.compareTo(b.startAt)))
          .where((game) => game.startAt.isAfter(now.toUtc()))
          .take(5)
          .toList(growable: false);
  Future<void> load({
    required String principalScope,
    required List<Game> games,
    required bool online,
  }) async {
    final nextWindow = selectWindow(games, _clock());
    final nextContext =
        '$principalScope|$online|${nextWindow.map((game) => game.id).join(',')}';
    if (_contextKey != nextContext) {
      _generation++;
      _contextKey = nextContext;
      if (_principalScope != principalScope) {
        _known.clear();
        _inFlight.clear();
        _principalScope = principalScope;
      }
    }
    final generation = _generation;
    window = nextWindow;
    if (window.isEmpty) {
      state = MemberActionState.empty;
      notifyListeners();
      return;
    }
    if (!online) {
      _project(online: false);
      return;
    }
    state = MemberActionState.loading;
    notifyListeners();
    var failed = false;
    final missing =
        window.where((game) => !_known.containsKey(game.id)).toList();
    for (var start = 0; start < missing.length; start += 3) {
      try {
        await Future.wait(
          missing.skip(start).take(3).map(
                (game) => _readOnce(game, generation),
              ),
        );
      } on Object {
        failed = true;
      }
    }
    if (generation != _generation) return;
    if (failed && unknown.isNotEmpty) {
      state = MemberActionState.retryableError;
      notifyListeners();
    } else {
      _project(online: true);
    }
  }

  Future<void> _readOnce(Game game, int generation) {
    final key = '$generation:${game.id}';
    return _inFlight.putIfAbsent(key, () async {
      try {
        final reply = (await _read(game.id)).ownReply;
        if (generation == _generation) _known[game.id] = reply;
      } finally {
        _inFlight.remove(key);
      }
    });
  }

  Future<void> refreshGame(Game game, {required bool online}) async {
    if (!online || !window.any((item) => item.id == game.id)) return;
    _known.remove(game.id);
    try {
      final generation = _generation;
      await _readOnce(game, generation);
      if (generation != _generation) return;
      _project(online: true);
    } on Object {
      state = MemberActionState.retryableError;
      notifyListeners();
    }
  }

  void remember(String gameId, AttendanceReply? reply) {
    _known[gameId] = reply;
  }

  void _project({required bool online}) {
    state = unknown.isNotEmpty
        ? MemberActionState.partialUnknown
        : pending.isNotEmpty
            ? MemberActionState.actionable
            : MemberActionState.resolved;
    notifyListeners();
  }

  String message({required bool online}) => switch (state) {
        MemberActionState.loading => '正在確認近期待辦…',
        MemberActionState.actionable =>
          '最近待處理：${nearestAction!.homeTeam ?? '主隊'} vs ${nearestAction!.awayTeam ?? '客隊'}',
        MemberActionState.resolved => '近期待辦皆已確認。',
        MemberActionState.partialUnknown => online
            ? '部分賽事尚無法確認回覆狀態。'
            : '離線時無法確認 ${unknown.length} 場的回覆狀態；未知不列為待處理。',
        MemberActionState.empty => '目前沒有已載入的未來賽事。',
        MemberActionState.retryableError => '暫時無法確認部分回覆，可稍後重試。',
      };
}

class NextAuthorizedGameCard extends StatefulWidget {
  const NextAuthorizedGameCard(
      {super.key,
      required this.api,
      required this.game,
      required this.online,
      required this.onOpen});
  final BasicApi api;
  final Game game;
  final bool online;
  final VoidCallback onOpen;
  @override
  State<NextAuthorizedGameCard> createState() => _NextAuthorizedGameCardState();
}

class _NextAuthorizedGameCardState extends State<NextAuthorizedGameCard> {
  Future<AttendanceSnapshot>? _attendance;
  @override
  void initState() {
    super.initState();
    if (widget.online) _attendance = widget.api.attendance(widget.game.id);
  }

  @override
  Widget build(BuildContext context) => AppSurfaceCard(
        child: ListTile(
          key: ValueKey('game-${widget.game.id}'),
          title:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
                '${widget.game.homeTeam ?? '主隊'} vs ${widget.game.awayTeam ?? '客隊'}'),
            if (widget.online)
              FutureBuilder<AttendanceSnapshot>(
                future: _attendance,
                builder: (_, snapshot) => Text(snapshot.hasData
                    ? '我的回覆：${snapshot.data!.ownReply?.wire ?? '尚未回覆'}'
                    : '出席載入中'),
              )
            else
              const Text('離線・非最新'),
          ]),
          subtitle: Text(_formatGameMetadata(
              MaterialLocalizations.of(context), widget.game)),
          trailing: const Icon(Icons.chevron_right),
          onTap: widget.online ? widget.onOpen : null,
        ),
      );
}

enum PublishingAudience { individual, game, team }

class OfficerNotificationPublishingPage extends StatefulWidget {
  const OfficerNotificationPublishingPage({
    super.key,
    required this.client,
    required this.games,
    this.ids,
  });
  final NotificationPublishingClient client;
  final List<Game> games;
  final SecureIds? ids;
  @override
  State<OfficerNotificationPublishingPage> createState() =>
      _OfficerNotificationPublishingPageState();
}

class _OfficerNotificationPublishingPageState
    extends State<OfficerNotificationPublishingPage> {
  final _title = TextEditingController();
  final _body = TextEditingController();
  final _personId = TextEditingController();
  final _confirmation = TextEditingController();
  PublishingAudience audience = PublishingAudience.team;
  String? gameId;
  Map<String, dynamic>? preview;
  Map<String, dynamic>? draft;
  String? commandKey;
  String? outcome;
  bool busy = false;
  late final SecureIds _ids;

  @override
  void initState() {
    super.initState();
    _ids = widget.ids ?? SecureIds();
    if (widget.games.isNotEmpty) gameId = widget.games.first.id;
  }

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    _personId.dispose();
    _confirmation.dispose();
    super.dispose();
  }

  Map<String, dynamic> _draft() {
    final audienceValue = switch (audience) {
      PublishingAudience.individual => {
          'type': 'individual',
          'person_id': _personId.text.trim(),
        },
      PublishingAudience.game => {'type': 'game', 'game_id': gameId},
      PublishingAudience.team => {'type': 'team'},
    };
    return {
      'type': switch (audience) {
        PublishingAudience.individual => 'officer_personal',
        PublishingAudience.game => 'officer_game_broadcast',
        PublishingAudience.team => 'officer_team_broadcast',
      },
      'title': _title.text.trim(),
      'body': _body.text.trim(),
      'audience': audienceValue,
      'destination': audience == PublishingAudience.game
          ? {'type': 'game', 'game_id': gameId}
          : {'type': 'notification'},
    };
  }

  Future<void> _preview() async {
    if (busy) return;
    setState(() {
      busy = true;
      preview = null;
      commandKey = null;
      outcome = null;
    });
    try {
      final nextDraft = _draft();
      final nextPreview = await widget.client.preview(nextDraft);
      if (!mounted) return;
      setState(() {
        draft = nextDraft;
        preview = nextPreview;
        commandKey = _ids.next();
        _confirmation.clear();
      });
    } on Object {
      if (mounted) setState(() => outcome = '預覽失敗，未發布任何通知');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _confirm() async {
    final currentPreview = preview;
    final currentDraft = draft;
    final currentKey = commandKey;
    if (busy ||
        currentPreview == null ||
        currentDraft == null ||
        currentKey == null) {
      return;
    }
    if (_confirmation.text != currentPreview['confirmation_text']) return;
    setState(() => busy = true);
    try {
      await widget.client.confirm(currentDraft, currentPreview, currentKey);
      if (!mounted) return;
      setState(() {
        preview = null;
        draft = null;
        commandKey = null;
        outcome = '通知已保存；外部推播結果不影響 App 內通知紀錄';
      });
    } on Object {
      if (mounted) setState(() => outcome = '發布失敗；請重新預覽收件人');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('發布隊務通知')),
        body: ListView(
          padding: const EdgeInsets.all(AppSpacing.regular),
          children: [
            DropdownButtonFormField<PublishingAudience>(
              key: const ValueKey('publishing-audience'),
              initialValue: audience,
              decoration: const InputDecoration(labelText: '收件範圍'),
              items: const [
                DropdownMenuItem(
                  value: PublishingAudience.individual,
                  child: Text('個人'),
                ),
                DropdownMenuItem(
                  value: PublishingAudience.game,
                  child: Text('賽事成員'),
                ),
                DropdownMenuItem(
                    value: PublishingAudience.team, child: Text('全隊')),
              ],
              onChanged: busy
                  ? null
                  : (value) => setState(() {
                        audience = value ?? PublishingAudience.team;
                        preview = null;
                      }),
            ),
            if (audience == PublishingAudience.individual)
              TextField(
                key: const ValueKey('publishing-person-id'),
                controller: _personId,
                decoration: const InputDecoration(labelText: 'Person ID'),
              ),
            if (audience == PublishingAudience.game)
              DropdownButtonFormField<String>(
                key: const ValueKey('publishing-game-id'),
                initialValue: gameId,
                decoration: const InputDecoration(labelText: '賽事'),
                items: [
                  for (final game in widget.games)
                    DropdownMenuItem(value: game.id, child: Text(game.id)),
                ],
                onChanged: busy
                    ? null
                    : (value) => setState(() {
                          gameId = value;
                          preview = null;
                        }),
              ),
            TextField(
              key: const ValueKey('publishing-title'),
              controller: _title,
              maxLength: 120,
              decoration: const InputDecoration(labelText: '標題'),
            ),
            TextField(
              key: const ValueKey('publishing-body'),
              controller: _body,
              maxLength: 500,
              maxLines: 5,
              decoration: const InputDecoration(labelText: '純文字內容'),
            ),
            FilledButton(
              key: const ValueKey('publishing-preview'),
              onPressed: busy ? null : _preview,
              child: const Text('預覽收件人'),
            ),
            if (preview != null) ...[
              Semantics(
                key: const ValueKey('publishing-preview-result'),
                liveRegion: true,
                label: '預覽收件人 ${preview!['recipient_count']} 人',
                child: Text('預覽收件人：${preview!['recipient_count']} 人'),
              ),
              TextField(
                key: const ValueKey('publishing-confirmation'),
                controller: _confirmation,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(
                  labelText: '請輸入 ${preview!['confirmation_text']}',
                ),
              ),
              FilledButton.tonal(
                key: const ValueKey('publishing-confirm'),
                onPressed:
                    !busy && _confirmation.text == preview!['confirmation_text']
                        ? _confirm
                        : null,
                child: const Text('確認發布'),
              ),
            ],
            if (outcome != null)
              Semantics(
                key: const ValueKey('publishing-outcome'),
                liveRegion: true,
                child: Text(outcome!),
              ),
          ],
        ),
      );
}

String _formatGameMetadata(MaterialLocalizations localizations, Game game) {
  final localStart = game.startAt.toLocal();
  final date = localizations.formatFullDate(localStart);
  final time = localizations.formatTimeOfDay(
    TimeOfDay.fromDateTime(localStart),
  );
  final details = <String>['$date $time'];
  if (game.location != null && game.location!.isNotEmpty) {
    details.add(game.location!);
  }
  if (game.durationMinutes != null) {
    details.add('${game.durationMinutes} 分鐘');
  }
  return details.join('・');
}

class AccountDataStatusPage extends StatefulWidget {
  const AccountDataStatusPage({
    super.key,
    required this.person,
    required this.lastSyncedAt,
    this.provenance,
    this.identityLink,
    this.platform,
  });

  final Person person;
  final DateTime lastSyncedAt;
  final PrincipalProvenance? provenance;
  final IdentityLinkController? identityLink;
  final String? platform;

  @override
  State<AccountDataStatusPage> createState() => _AccountDataStatusPageState();
}

class _AccountDataStatusPageState extends State<AccountDataStatusPage> {
  @override
  void initState() {
    super.initState();
    widget.identityLink?.loadLinkedMethods();
  }

  @override
  Widget build(BuildContext context) {
    final localizations = MaterialLocalizations.of(context);
    final localLastSyncedAt = widget.lastSyncedAt.toLocal();
    final source = switch (widget.provenance) {
      PrincipalProvenance.freshServer => '資料來源：伺服器同步資料',
      PrincipalProvenance.offlineCache => '資料來源：離線快取，唯讀且非權威',
      null => '資料來源未確認，請勿視為權威',
    };
    final description = switch (widget.provenance) {
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
            label: '目前帳號：${widget.person.displayName}',
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.person_outline),
              title: Text(widget.person.displayName),
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
                '${localizations.formatFullDate(localLastSyncedAt)} ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(localLastSyncedAt))}',
              ),
            ),
          ),
          const Divider(),
          Semantics(
            key: const ValueKey('account-data-provenance'),
            label: '$source $description',
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                widget.provenance == PrincipalProvenance.freshServer
                    ? Icons.cloud_done_outlined
                    : Icons.cloud_off,
              ),
              title: Text(source),
              subtitle: Text(description),
            ),
          ),
          if (widget.identityLink != null && widget.platform != null) ...[
            const Divider(),
            IdentityLinkPanel(
              controller: widget.identityLink!,
              platform: widget.platform!,
            ),
          ],
        ],
      ),
    );
  }
}

class DebugPrincipalProjection extends StatelessWidget {
  const DebugPrincipalProjection({
    super.key,
    required this.person,
    required this.provenance,
  });

  final Person person;
  final PrincipalProvenance? provenance;

  static bool shouldRender({
    required bool debugBuild,
    required bool diagnosticEnabled,
  }) =>
      debugBuild && diagnosticEnabled;

  static String localizedRole(AccessLevel accessLevel) => switch (accessLevel) {
        AccessLevel.basic => '一般使用者',
        AccessLevel.officer => '幹部',
        AccessLevel.admin => '系統管理者',
      };

  static (String, String) localizedProvenance(
    PrincipalProvenance? provenance,
  ) =>
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
        subtitle: Text(
          '報表讀取：$reportRead；來源：$provenanceToken（$provenanceLabel）',
        ),
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
  sessionExpired,
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

  static CanonicalOwnReplyObservation fromReply(
    AttendanceReply? reply,
  ) =>
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

class CachedGameDetailPage extends StatelessWidget {
  const CachedGameDetailPage({super.key, required this.game});

  final Game game;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('賽事')),
        body: ListView(
          padding: const EdgeInsets.all(AppSpacing.regular),
          children: [
            const AppStatusPanel(
              icon: Icons.cloud_off,
              title: '離線唯讀模式',
              message: '離線快取賽事，僅供查看。',
            ),
            const SizedBox(height: AppSpacing.regular),
            AppSurfaceCard(
              padding: const EdgeInsets.all(AppSpacing.regular),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${game.homeTeam ?? '主隊'} vs ${game.awayTeam ?? '客隊'}',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: AppSpacing.compact),
                  Text(
                    _formatGameMetadata(
                        MaterialLocalizations.of(context), game),
                    key: const ValueKey('cached-game-detail-metadata'),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
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
              child: SizedBox(
                width: 320,
                child: AppStatusPanel(
                  icon: Icons.sports_basketball_outlined,
                  title: '正在載入賽事與出席',
                  loading: true,
                ),
              ),
            ),
          DetailViewState.error => const AuthStatePanel(
              state: AuthViewState.recoverableError,
            ),
          DetailViewState.mutationError => Semantics(
              key: const ValueKey('mutation-error'),
              label: '出席回覆失敗，未變更目前結果',
              liveRegion: true,
              child: const Center(
                child: SizedBox(
                  width: 320,
                  child: AppStatusPanel(
                    icon: Icons.error_outline,
                    title: '出席回覆失敗',
                    message: '請確認狀態後重試。',
                    liveRegion: true,
                  ),
                ),
              ),
            ),
          DetailViewState.contractError => const AuthStatePanel(
              state: AuthViewState.contractError,
            ),
          DetailViewState.sessionExpired => const AuthStatePanel(
              state: AuthViewState.sessionExpired,
            ),
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
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.regular),
      children: [
        AppSurfaceCard(
          padding: const EdgeInsets.all(AppSpacing.regular),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${game!.homeTeam ?? '主隊'} vs ${game!.awayTeam ?? '客隊'}',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: AppSpacing.compact),
              Text(
                _formatGameMetadata(localizations, game!),
                key: const ValueKey('game-detail-metadata'),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.regular),
        if (observation != null &&
            DebugAuthoritativeOwnReplyProjection.shouldRender(
              debugBuild: kDebugMode,
              diagnosticEnabled: widget.diagnosticEnabled,
            ))
          DebugAuthoritativeOwnReplyProjection(
            observation: observation.$1,
            source: observation.$2,
          ),
        AppSurfaceCard(
          padding: const EdgeInsets.all(AppSpacing.regular),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('我的出席回覆'),
              if (state == DetailViewState.uncertain)
                Semantics(
                  key: const ValueKey('mutation-uncertain'),
                  label: '回覆結果待確認，已保留同一操作識別碼',
                  liveRegion: true,
                  child: const Text('回覆結果待確認，請稍後以同一回覆重試。'),
                ),
              Wrap(
                spacing: 8,
                children: AttendanceReply.values
                    .map(
                      (reply) => ChoiceChip(
                        key: ValueKey('reply-${reply.wire}'),
                        label: Text(_replyLabel(reply)),
                        selected: selected == reply,
                        onSelected: state == DetailViewState.mutating
                            ? null
                            : (_) => setState(() => selected = reply),
                      ),
                    )
                    .toList(),
              ),
              FilledButton(
                onPressed: state == DetailViewState.mutating ? null : _submit,
                child: Text(state == DetailViewState.mutating ? '送出中' : '送出回覆'),
              ),
              const Divider(),
              const Text('已回覆隊員'),
              for (final reply in attendance!.replied)
                ListTile(
                  title: Text(reply.displayName),
                  subtitle: Text(
                    '${_qualificationLabel(reply.qualification)}・${_replyLabel(reply.reply)}',
                  ),
                ),
            ],
          ),
        ),
      ],
    );
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
