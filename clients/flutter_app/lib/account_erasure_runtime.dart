import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:http/http.dart' as http;

import 'account_erasure_entry.dart';
import 'anonymous_crash.dart';
import 'basic_app.dart';
import 'foundation.dart';
import 'google_authorization.dart';
import 'integration.dart';

/// This is only an entry activation gate, never backend erasure readiness.
bool accountErasureEnabled(
    String value, AppConfig config, TargetPlatform platform) {
  if (value.isEmpty || value == 'false') {
    return false;
  }
  if (value != 'true' ||
      config.flavor != AppFlavor.staging ||
      config.mode != ClientMode.real ||
      !{TargetPlatform.iOS, TargetPlatform.android}.contains(platform) ||
      kIsWeb) {
    throw const FormatException('invalid_account_erasure_runtime');
  }
  return true;
}

/// A dedicated, credential-free client per probe; no cookies, auth interceptor,
/// redirect, timer, provider call or business session is used. Success means
/// reachability only. All failures/unknown/suspended states remain offline.
class ErasureReachability extends ChangeNotifier {
  ErasureReachability(Uri apiBaseUrl,
      {http.Client Function()? clientFactory,
      this.timeout = const Duration(seconds: 5)})
      : _uri = apiBaseUrl.replace(path: '/health', query: null, fragment: null),
        _clientFactory = clientFactory ?? http.Client {
    if (apiBaseUrl.scheme != 'https' ||
        apiBaseUrl.host.isEmpty ||
        apiBaseUrl.userInfo.isNotEmpty ||
        apiBaseUrl.hasQuery ||
        apiBaseUrl.hasFragment ||
        timeout <= Duration.zero) {
      throw const FormatException('invalid_erasure_probe');
    }
  }

  final Uri _uri;
  final http.Client Function() _clientFactory;
  final Duration timeout;
  bool _online = false;
  bool _active = true;
  bool _disposed = false;
  bool _resumeQueued = false;
  int _epoch = 0;
  Future<void>? _pending;
  Completer<void>? _resumed;
  http.Client? _client;
  bool get online => !_disposed && _active && _online;

  void _setOnline(bool value) {
    if (_disposed || _online == value) {
      return;
    }
    _online = value;
    notifyListeners();
  }

  Future<void> refresh() {
    if (_disposed) {
      return Future<void>.value();
    }
    if (!_active) {
      return _waitForResume();
    }
    if (_pending != null) {
      return _pending!;
    }
    final completion = Completer<void>();
    // Reserve before notification: a listener may synchronously ask to refresh.
    _pending = completion.future;
    unawaited(_probeCycle().whenComplete(() {
      _pending = null;
      completion.complete();
    }));
    return completion.future;
  }

  Future<void> _waitForResume() async {
    try {
      await (_resumed ??= Completer<void>()).future.timeout(timeout);
      if (!_disposed && _active) {
        await refresh();
      }
    } on Object {
      // No resume acknowledgement means offline, not permission to submit.
    }
  }

  Future<void> _probeCycle() async {
    _resumeQueued = false;
    await _probe();
    if (_resumeQueued && !_disposed && _active) {
      _resumeQueued = false;
      await _probe();
    }
    _resumeQueued = false;
  }

  Future<void> _probe() async {
    final epoch = _epoch;
    _setOnline(false);
    http.Client? client;
    try {
      client = _clientFactory();
      _client = client;
      final success = await (() async {
        final request = http.Request('GET', _uri)
          ..followRedirects = false
          ..maxRedirects = 0;
        final response = await client!.send(request);
        if (response.statusCode != 200 ||
            (response.contentLength != null &&
                response.contentLength! > 1024)) {
          return false;
        }
        var size = 0;
        await for (final chunk in response.stream) {
          size += chunk.length;
          if (size > 1024) {
            return false;
          }
        }
        return true;
      })()
          .timeout(timeout);
      if (!_disposed && _active && epoch == _epoch) {
        _setOnline(success);
      }
    } on Object {
      if (!_disposed && epoch == _epoch) {
        _setOnline(false);
      }
    } finally {
      client?.close();
      if (identical(_client, client)) {
        _client = null;
      }
    }
  }

  void lifecycle(AppLifecycleState state) {
    if (_disposed) {
      return;
    }
    if (state != AppLifecycleState.resumed) {
      _active = false;
      _epoch++;
      _resumeQueued = false;
      _setOnline(false);
      _client?.close();
      return;
    }
    _active = true;
    _resumed?.complete();
    _resumed = null;
    if (_pending != null) {
      _resumeQueued = true;
    } else {
      unawaited(refresh());
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _active = false;
    _epoch++;
    _resumed?.complete();
    _resumed = null;
    _client?.close();
    super.dispose();
  }
}

/// All real main paths share this gate. Disabled returns the existing root and
/// does not construct an erasure port, owner, store or probe. Ordinary bootstrap
/// still owns its existing session/store and only creates an owner after consent.
Widget composeAccountErasureRoot({
  required AppConfig config,
  DurableStore? store,
  AnonymousCrashQueue? crashQueue,
  String enabled = const String.fromEnvironment('ACCOUNT_ERASURE_ENABLED'),
  TargetPlatform? platform,
  // Fake-only seams. Main leaves both null; disabled never invokes either.
  http.Client Function()? probeClientFactory,
  Widget Function(AccountErasureEntryOptions)? enabledBuilder,
}) {
  final target = platform ?? defaultTargetPlatform;
  if (!accountErasureEnabled(enabled, config, target)) {
    return BasicBootstrapApp(
        config: config, store: store, crashQueue: crashQueue);
  }
  return _ErasureRuntimeRoot(
    config: config,
    store: store,
    crashQueue: crashQueue,
    platform: target,
    clientFactory: probeClientFactory,
    builder: enabledBuilder,
  );
}

class _ErasureRuntimeRoot extends StatefulWidget {
  const _ErasureRuntimeRoot(
      {required this.config,
      required this.platform,
      this.store,
      this.crashQueue,
      this.clientFactory,
      this.builder});
  final AppConfig config;
  final TargetPlatform platform;
  final DurableStore? store;
  final AnonymousCrashQueue? crashQueue;
  final http.Client Function()? clientFactory;
  final Widget Function(AccountErasureEntryOptions)? builder;
  @override
  State<_ErasureRuntimeRoot> createState() => _ErasureRuntimeRootState();
}

class _ErasureRuntimeRootState extends State<_ErasureRuntimeRoot>
    with WidgetsBindingObserver {
  late ErasureReachability _reachability;
  late AccountErasureEntryOptions _options;
  late Object _rootIdentity;

  void _initialize() {
    _rootIdentity = Object();
    _reachability = ErasureReachability(widget.config.apiBaseUrl!,
        clientFactory: widget.clientFactory);
    final reachability = _reachability;
    _options = AccountErasureEntryOptions(
      isOnline: () => reachability.online,
      connectivity: _reachability,
      refreshConnectivity: _reachability.refresh,
      google: NativeGoogleAuthorization(
          widget.platform == TargetPlatform.iOS ? 'ios' : 'android',
          widget.config.googleClientId!,
          widget.config.googleServerClientId!),
    );
    _reachability.lifecycle(
        WidgetsBinding.instance.lifecycleState ?? AppLifecycleState.resumed);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initialize();
  }

  @override
  void didUpdateWidget(_ErasureRuntimeRoot oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.config, widget.config) ||
        oldWidget.platform != widget.platform ||
        !identical(oldWidget.store, widget.store)) {
      _reachability.dispose();
      _initialize();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) =>
      _reachability.lifecycle(state);

  @override
  Widget build(BuildContext context) =>
      widget.builder?.call(_options) ??
      BasicBootstrapApp(
          config: widget.config,
          store: widget.store,
          key: ObjectKey(_rootIdentity),
          crashQueue: widget.crashQueue,
          erasureEntry: _options);

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _reachability.dispose();
    super.dispose();
  }
}
