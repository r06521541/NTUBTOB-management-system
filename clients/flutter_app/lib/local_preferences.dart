import 'package:flutter/material.dart';

import 'app_theme.dart';
import 'integration.dart';

enum LocalThemePreference { system, light, dark }

extension LocalThemePreferenceMode on LocalThemePreference {
  ThemeMode get themeMode => switch (this) {
        LocalThemePreference.system => ThemeMode.system,
        LocalThemePreference.light => ThemeMode.light,
        LocalThemePreference.dark => ThemeMode.dark,
      };
}

/// These values are installation-only: no Person id is used in their keys.
class LocalPreferences {
  const LocalPreferences(this.store, this.installationId);
  final DurableStore store;
  final String installationId;
  String get _prefix => 'local-preferences:v1:$installationId:';

  Future<LocalThemePreference> theme() async =>
      switch (await store.read('${_prefix}theme')) {
        'light' => LocalThemePreference.light,
        'dark' => LocalThemePreference.dark,
        _ => LocalThemePreference.system,
      };
  Future<void> saveTheme(LocalThemePreference value) =>
      store.write('${_prefix}theme', value.name);
  Future<bool> onboardingComplete() async =>
      await store.read('${_prefix}onboarding') == 'complete';
  Future<void> completeOnboarding() =>
      store.write('${_prefix}onboarding', 'complete');
}

abstract interface class NotificationPermissionPort {
  Future<bool> requestPermission();
  Future<void> openSystemSettings();
}

/// The app never calls this from boot/build; UI invokes only these explicit
/// user-action methods.  The port keeps platform providers out of tests.
class NotificationPermissionActions {
  const NotificationPermissionActions(this.port);
  final NotificationPermissionPort port;
  Future<bool> requestAfterExplicitTap() => port.requestPermission();
  Future<void> openSettingsAfterExplicitTap() => port.openSystemSettings();
}

class UnsupportedNotificationPermissionPort
    implements NotificationPermissionPort {
  const UnsupportedNotificationPermissionPort();
  @override
  Future<bool> requestPermission() async => false;
  @override
  Future<void> openSystemSettings() async {}
}

class LocalPreferencesPage extends StatefulWidget {
  const LocalPreferencesPage(
      {super.key,
      required this.preferences,
      required this.permissions,
      required this.onThemeChanged});
  final LocalPreferences preferences;
  final NotificationPermissionActions permissions;
  final ValueChanged<LocalThemePreference> onThemeChanged;
  @override
  State<LocalPreferencesPage> createState() => _LocalPreferencesPageState();
}

class _LocalPreferencesPageState extends State<LocalPreferencesPage> {
  LocalThemePreference _theme = LocalThemePreference.system;
  @override
  void initState() {
    super.initState();
    widget.preferences.theme().then((value) {
      if (mounted) setState(() => _theme = value);
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('App 偏好設定')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const AppPageTitle(
          eyebrow: 'PREFERENCES',
          title: 'App 偏好設定',
          subtitle: '調整只儲存在這台裝置上的顯示與通知選項。',
        ),
        const SizedBox(height: 16),
        const ListTile(title: Text('外觀')),
        ListTile(
          title: const Text('主題'),
          trailing: DropdownButton<LocalThemePreference>(
            key: const ValueKey('theme-preference'),
            value: _theme,
            items: [
              for (final value in LocalThemePreference.values)
                DropdownMenuItem(value: value, child: Text(value.name)),
            ],
            onChanged: (next) async {
              if (next == null) return;
              await widget.preferences.saveTheme(next);
              widget.onThemeChanged(next);
              if (mounted) setState(() => _theme = next);
            },
          ),
        ),
        const Divider(),
        const ListTile(title: Text('通知')),
        ListTile(
            title: const Text('要求通知權限'),
            subtitle: const Text('只在您點擊後請求系統權限'),
            key: const ValueKey('request-notification-permission'),
            onTap: () => widget.permissions.requestAfterExplicitTap()),
        ListTile(
            title: const Text('開啟系統設定'),
            subtitle: const Text('若已拒絕，請自行在系統設定變更'),
            key: const ValueKey('open-notification-settings'),
            onTap: () => widget.permissions.openSettingsAfterExplicitTap()),
      ]));
}

class OnboardingPage extends StatefulWidget {
  const OnboardingPage({super.key, required this.onComplete});
  final Future<void> Function() onComplete;
  @override
  State<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends State<OnboardingPage> {
  final _controller = PageController();
  int _page = 0;
  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(actions: [
          TextButton(
              key: const ValueKey('skip-onboarding'),
              onPressed: widget.onComplete,
              child: const Text('跳過'))
        ]),
        body: PageView(
            controller: _controller,
            onPageChanged: (value) => setState(() => _page = value),
            children: const [
              Padding(
                padding: EdgeInsets.all(24),
                child: AppPageTitle(
                  eyebrow: 'WELCOME',
                  title: '歡迎使用隊務系統',
                  subtitle: '用同一個入口掌握賽事、回覆與隊務通知。',
                ),
              ),
              Padding(
                padding: EdgeInsets.all(24),
                child: AppPageTitle(
                  eyebrow: 'MEMBER PORTAL',
                  title: '賽事與通知',
                  subtitle: '只有登入並通過授權後才會顯示。',
                ),
              ),
              Padding(
                padding: EdgeInsets.all(24),
                child: AppNoticePanel(
                  title: '離線仍保持誠實',
                  message: '離線資料會明確標示為唯讀且可能不是最新。',
                ),
              ),
            ]),
        floatingActionButton: _page == 2
            ? FloatingActionButton.extended(
                key: const ValueKey('complete-onboarding'),
                onPressed: widget.onComplete,
                label: const Text('開始使用'))
            : FloatingActionButton(
                key: const ValueKey('next-onboarding'),
                onPressed: () => _controller.nextPage(
                    duration: const Duration(milliseconds: 200),
                    curve: Curves.easeOut),
                child: const Icon(Icons.arrow_forward)),
      );
}
