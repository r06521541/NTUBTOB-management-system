import 'package:flutter/material.dart';

enum AppFlavor { development, staging, production }
enum Persona { basic, officer, admin }
enum LoadState { loading, empty, ready, error, offline }

class FlavorConfig {
  const FlavorConfig(this.flavor);
  final AppFlavor flavor;
  String get label => flavor.name;
  String get displayLabel => switch (flavor) {
        AppFlavor.development => '開發預覽',
        AppFlavor.staging => '測試預覽',
        AppFlavor.production => '產品預覽',
      };
}

class CapabilityPolicy {
  const CapabilityPolicy(this.persona);
  final Persona persona;
  bool get canViewOfficer => persona.index >= Persona.officer.index;
  bool get canViewAdmin => persona == Persona.admin;
  List<String> get routes => [
        '/', '/schedule', '/notifications', '/account',
        if (canViewOfficer) '/officer',
        if (canViewAdmin) '/admin',
      ];
}

class DemoSnapshot {
  const DemoSnapshot({required this.lastSyncedAt, this.fixture = DemoFixtures.account});
  final DateTime lastSyncedAt;
  final Map<String, Object> fixture;
}

class DemoFixtures {
  static const Map<String, Object> account = <String, Object>{
    'account': '示範會員',
    'schedule': <String>['週三練習', '週六友誼賽'],
    'replies': <String>['示範會員：參加', '隊友甲：待確認'],
    'notifications': <String>['賽程已更新'],
    'officerSummary': '本週回覆率 80%',
    'adminAnnouncement': '系統公告預覽',
  };
}

abstract class DemoRepository {
  Future<DemoSnapshot> readSnapshot();
  Future<void> submitOfflineMutation();
}

class FakeRepository implements DemoRepository {
  FakeRepository({DateTime? lastSyncedAt})
      : _snapshot = DemoSnapshot(
          lastSyncedAt: lastSyncedAt ?? DateTime.utc(2026, 8, 18, 8),
        );
  final DemoSnapshot _snapshot;
  final List<String> pushEvents = <String>[];
  @override
  Future<DemoSnapshot> readSnapshot() async => _snapshot;
  @override
  Future<void> submitOfflineMutation() async {
    throw StateError('離線模式僅供讀取');
  }
}

class DemoApp extends StatelessWidget {
  const DemoApp({super.key, this.persona = Persona.basic, this.flavor = AppFlavor.development});
  final Persona persona;
  final AppFlavor flavor;
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'NTUBTOB fictional client',
        theme: ThemeData(colorSchemeSeed: Colors.indigo, brightness: Brightness.light),
        darkTheme: ThemeData(colorSchemeSeed: Colors.indigo, brightness: Brightness.dark),
        themeMode: ThemeMode.system,
        initialRoute: '/',
        onGenerateRoute: (settings) {
          final policy = CapabilityPolicy(persona);
          final allowed = policy.routes.contains(settings.name);
          return MaterialPageRoute<void>(
            builder: (_) => allowed
                ? DemoShell(title: settings.name == '/' ? '首頁' : settings.name!.substring(1))
                : const StatePanel(state: LoadState.error, message: '此預覽角色沒有此頁面'),
          );
        },
      );
}

class DemoShell extends StatelessWidget {
  const DemoShell({super.key, required this.title});
  final String title;
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(title)),
        body: Center(child: Text('fictional $title')),
        bottomNavigationBar: NavigationBar(destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: '首頁'),
          NavigationDestination(icon: Icon(Icons.event_outlined), label: '賽程'),
          NavigationDestination(icon: Icon(Icons.notifications_outlined), label: '通知'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: '帳號'),
        ]),
      );
}

class StatePanel extends StatelessWidget {
  const StatePanel({super.key, required this.state, required this.message});
  final LoadState state;
  final String message;
  @override
  Widget build(BuildContext context) => Center(child: Text(message));
}
