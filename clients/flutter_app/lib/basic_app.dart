import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'foundation.dart';
import 'integration.dart';

enum AuthViewState {
  signedOut,
  pending,
  cancelled,
  error,
  unavailable,
  logoutPending,
  offline,
  authenticated
}

class AuthStatePanel extends StatelessWidget {
  const AuthStatePanel({super.key, required this.state});
  final AuthViewState state;
  @override
  Widget build(BuildContext context) {
    final (icon, label) = switch (state) {
      AuthViewState.signedOut => (Icons.login, '請使用 LINE 安全登入'),
      AuthViewState.pending => (Icons.hourglass_top, '登入處理中'),
      AuthViewState.cancelled => (Icons.cancel_outlined, '已取消登入'),
      AuthViewState.error => (Icons.error_outline, '登入失敗，請稍後重試'),
      AuthViewState.unavailable => (Icons.mobile_off, '此裝置無法使用 LINE 登入'),
      AuthViewState.logoutPending => (Icons.logout, '登出同步中，暫停操作'),
      AuthViewState.offline => (Icons.cloud_off, '離線唯讀模式'),
      AuthViewState.authenticated => (Icons.verified_user_outlined, '已安全登入'),
    };
    return Semantics(
      label: label,
      liveRegion: true,
      child: Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
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
  AuthViewState state = AuthViewState.pending;
  late final http.Client _http;
  LoginCoordinator? _login;
  SessionController? _session;
  BasicApi? _api;
  LineLoginPort? _line;
  BasicCache? _cache;
  Person? person;
  List<Game> games = const [];
  DateTime? lastSyncedAt;

  @override
  void initState() {
    super.initState();
    _http = http.Client();
    _boot();
  }

  Future<void> _boot() async {
    final installationId = await _installationId();
    final transport = HttpApiTransport(widget.config.apiBaseUrl!, _http);
    final session = SessionController(transport, _store, installationId, _ids);
    final line = NativeLineLogin(widget.config.lineChannelId!);
    _session = session;
    _line = line;
    _api = BasicApi(session, _store, installationId, _ids);
    _cache = BasicCache(_store, installationId);
    _login = LoginCoordinator(line, transport, session, _ids, installationId);
    if (await _store.read('logout-pending:$installationId') == 'true') {
      setState(() => state = AuthViewState.logoutPending);
      try {
        await session.logout(line);
      } catch (_) {
        return;
      }
    }
    try {
      await session.refresh();
      await _loadBasic();
    } catch (_) {
      final cached = await _cache!.load();
      if (!mounted) return;
      setState(() {
        person = cached?.person;
        games = cached?.games ?? const [];
        lastSyncedAt = cached?.lastSyncedAt;
        state =
            cached == null ? AuthViewState.signedOut : AuthViewState.offline;
      });
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
    setState(() => state = AuthViewState.pending);
    await _login!.login(
        Theme.of(context).platform == TargetPlatform.iOS ? 'ios' : 'android');
    final result = _login!.state;
    if (result == LoginState.authenticated) {
      await _loadBasic();
      return;
    }
    if (!mounted) return;
    setState(() => state = switch (result) {
          LoginState.cancelled => AuthViewState.cancelled,
          LoginState.unavailable => AuthViewState.unavailable,
          _ => AuthViewState.error,
        });
  }

  Future<void> _loadBasic() async {
    try {
      final loadedPerson = await _api!.me();
      final loadedGames = await _api!.games();
      final syncedAt = DateTime.now().toUtc();
      await _cache!.save(loadedPerson, loadedGames, syncedAt);
      if (mounted) {
        setState(() {
          person = loadedPerson;
          games = loadedGames;
          lastSyncedAt = syncedAt;
          state = AuthViewState.authenticated;
        });
      }
    } catch (_) {
      final cached = await _cache!.load();
      if (mounted) {
        setState(() {
          person = cached?.person;
          games = cached?.games ?? const [];
          lastSyncedAt = cached?.lastSyncedAt;
          state = AuthViewState.offline;
        });
      }
    }
  }

  Future<void> _logout() async {
    setState(() => state = AuthViewState.logoutPending);
    try {
      await _session!.logout(_line!);
      await _cache!.clear();
      if (mounted) {
        setState(() {
          person = null;
          games = const [];
          state = AuthViewState.signedOut;
        });
      }
    } catch (_) {/* logout_pending intentionally blocks further actions */}
  }

  @override
  void dispose() {
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
          body: state == AuthViewState.authenticated
              ? ListView(children: [
                  ListTile(
                      title: Text(person!.displayName),
                      subtitle: const Text('Basic 帳號')),
                  for (final game in games)
                    ListTile(
                        title: Text(game.id),
                        subtitle: Text(game.startAt.toIso8601String())),
                ])
              : state == AuthViewState.offline && person != null
                  ? ListView(children: [
                      const ListTile(
                          leading: Icon(Icons.cloud_off),
                          title: Text('離線唯讀模式')),
                      ListTile(
                          title: Text(person!.displayName),
                          subtitle:
                              Text('最後同步：${lastSyncedAt!.toIso8601String()}')),
                      for (final game in games)
                        ListTile(
                            title: Text(game.id),
                            subtitle: Text(game.startAt.toIso8601String())),
                    ])
                  : AuthStatePanel(state: state),
          floatingActionButton: state == AuthViewState.signedOut ||
                  state == AuthViewState.cancelled ||
                  state == AuthViewState.error
              ? FloatingActionButton(
                  onPressed: _login == null ? null : _signIn,
                  tooltip: 'LINE 登入',
                  child: const Icon(Icons.login))
              : state == AuthViewState.authenticated
                  ? FloatingActionButton(
                      onPressed: _logout,
                      tooltip: '登出',
                      child: const Icon(Icons.logout))
                  : null,
        ),
      );
}
