import 'package:flutter/material.dart';

enum AppFlavor { development, staging, production }
enum Persona { basic, officer, admin }
enum LoadState { loading, empty, error, offline }

class FlavorConfig {
  const FlavorConfig(this.flavor);
  final AppFlavor flavor;

  static FlavorConfig parse(String value) => switch (value) {
        'development' => const FlavorConfig(AppFlavor.development),
        'staging' => const FlavorConfig(AppFlavor.staging),
        'production' => const FlavorConfig(AppFlavor.production),
        _ => throw ArgumentError.value(value, 'APP_FLAVOR', '未知環境，拒絕啟動'),
      };

  String get displayLabel => switch (flavor) {
        AppFlavor.development => '開發預覽',
        AppFlavor.staging => '測試預覽',
        AppFlavor.production => '產品預覽',
      };
}

class DemoDestination {
  const DemoDestination(this.route, this.label, this.icon, this.minimumPersona);
  final String route;
  final String label;
  final IconData icon;
  final Persona minimumPersona;
}

class CapabilityPolicy {
  const CapabilityPolicy(this.persona);
  final Persona persona;

  static const primaryDestinations = <DemoDestination>[
    DemoDestination('/', '首頁', Icons.home_outlined, Persona.basic),
    DemoDestination('/schedule', '賽程', Icons.event_outlined, Persona.basic),
    DemoDestination('/notifications', '通知', Icons.notifications_outlined, Persona.basic),
    DemoDestination('/account', '帳號', Icons.person_outline, Persona.basic),
    DemoDestination('/management', '管理', Icons.manage_accounts_outlined, Persona.officer),
  ];

  static const managementDestinations = <DemoDestination>[
    DemoDestination('/officer/attendance', '出席摘要', Icons.fact_check_outlined, Persona.officer),
    DemoDestination('/officer/personal', '個人通知', Icons.person_pin_outlined, Persona.officer),
    DemoDestination('/officer/broadcast', '通知廣播', Icons.send_outlined, Persona.officer),
    DemoDestination('/admin', '系統公告', Icons.campaign_outlined, Persona.admin),
  ];

  List<DemoDestination> get bottomDestinations => primaryDestinations
      .where((destination) => persona.index >= destination.minimumPersona.index)
      .toList(growable: false);

  List<DemoDestination> get visibleManagementDestinations => managementDestinations
      .where((destination) => persona.index >= destination.minimumPersona.index)
      .toList(growable: false);

  DemoDestination? destinationFor(String? route) {
    for (final destination in [...bottomDestinations, ...visibleManagementDestinations]) {
      if (destination.route == route) return destination;
    }
    return null;
  }
}

class DemoFixtures {
  const DemoFixtures({
    required this.account,
    required this.schedule,
    required this.replies,
    required this.notifications,
    required this.officerSummary,
    required this.adminAnnouncement,
  });
  final String account;
  final List<String> schedule;
  final List<String> replies;
  final List<String> notifications;
  final String officerSummary;
  final String adminAnnouncement;

  static const fictional = DemoFixtures(
    account: '示範會員',
    schedule: <String>['週三練習', '週六友誼賽'],
    replies: <String>['示範會員：參加', '隊友甲：待確認'],
    notifications: <String>['賽程已更新'],
    officerSummary: '本週回覆率 80%',
    adminAnnouncement: '系統公告預覽',
  );
}

class DemoSnapshot {
  const DemoSnapshot({required this.lastSyncedAt, this.fixtures = DemoFixtures.fictional});
  final DateTime lastSyncedAt;
  final DemoFixtures fixtures;
}

abstract class FakeApiRepository {
  Future<DemoSnapshot> readSnapshot();
  Future<void> submitOfflineMutation();
}

class InMemoryFakeApiRepository implements FakeApiRepository {
  InMemoryFakeApiRepository({DateTime? lastSyncedAt})
      : _snapshot = DemoSnapshot(lastSyncedAt: lastSyncedAt ?? DateTime.utc(2026, 8, 18, 8));
  final DemoSnapshot _snapshot;
  @override
  Future<DemoSnapshot> readSnapshot() async => _snapshot;
  @override
  Future<void> submitOfflineMutation() async => throw StateError('離線模式僅供讀取');
}

class FictionalPushEvent {
  const FictionalPushEvent(this.id, this.message);
  final String id;
  final String message;
}

abstract class PushRepository {
  List<FictionalPushEvent> get events;
  void record(FictionalPushEvent event);
}

class FakePushRepository implements PushRepository {
  final List<FictionalPushEvent> _events = <FictionalPushEvent>[];
  @override
  List<FictionalPushEvent> get events => List.unmodifiable(_events);
  @override
  void record(FictionalPushEvent event) => _events.add(event);
}

ThemeData demoTheme(Brightness brightness) =>
    ThemeData(colorSchemeSeed: Colors.indigo, brightness: brightness);

class DemoApp extends StatelessWidget {
  const DemoApp({super.key, this.persona = Persona.basic, required this.flavor});
  final Persona persona;
  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'NTUBTOB ${flavor.displayLabel}',
        theme: demoTheme(Brightness.light),
        darkTheme: demoTheme(Brightness.dark),
        themeMode: ThemeMode.system,
        home: DemoShell(persona: persona),
      );
}

class DemoShell extends StatefulWidget {
  const DemoShell({super.key, required this.persona});
  final Persona persona;
  @override
  State<DemoShell> createState() => _DemoShellState();
}

class _DemoShellState extends State<DemoShell> {
  int selectedIndex = 0;
  @override
  Widget build(BuildContext context) {
    final policy = CapabilityPolicy(widget.persona);
    final destinations = policy.bottomDestinations;
    final selected = destinations[selectedIndex];
    return Scaffold(
      appBar: AppBar(title: Text(selected.label)),
      body: selected.route == '/management'
          ? ManagementHub(policy: policy)
          : _DestinationPage(destination: selected),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: (index) => setState(() => selectedIndex = index),
        destinations: [
          for (final destination in destinations)
            NavigationDestination(icon: Icon(destination.icon), label: destination.label),
        ],
      ),
    );
  }
}

class ManagementHub extends StatelessWidget {
  const ManagementHub({super.key, required this.policy});
  final CapabilityPolicy policy;

  @override
  Widget build(BuildContext context) => ListView(
        key: const ValueKey('/management'),
        children: [
          for (final destination in policy.visibleManagementDestinations)
            ListTile(
              leading: Icon(destination.icon),
              title: Text(destination.label),
              onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => Scaffold(
                  appBar: AppBar(title: Text(destination.label)),
                  body: _DestinationPage(destination: destination),
                ),
              )),
            ),
        ],
      );
}

class _DestinationPage extends StatelessWidget {
  const _DestinationPage({required this.destination});
  final DemoDestination destination;

  @override
  Widget build(BuildContext context) {
    final detail = switch (destination.route) {
      '/' => '歡迎回到球隊 fictional 首頁',
      '/schedule' => DemoFixtures.fictional.schedule.join('、'),
      '/notifications' => DemoFixtures.fictional.notifications.join('、'),
      '/account' => DemoFixtures.fictional.account,
      '/management' => 'fictional 管理功能入口',
      '/officer/attendance' => DemoFixtures.fictional.officerSummary,
      '/officer/personal' => 'fictional 個人通知預覽',
      '/officer/broadcast' => 'fictional 通知廣播預覽',
      '/admin' => DemoFixtures.fictional.adminAnnouncement,
      _ => '拒絕顯示未知頁面',
    };
    return Center(
      key: ValueKey(destination.route),
      child: Column(mainAxisSize: MainAxisSize.min, children: [Text(destination.label), Text(detail)]),
    );
  }
}

class StatePanel extends StatelessWidget {
  const StatePanel({super.key, required this.state, this.lastSyncedAt});
  final LoadState state;
  final DateTime? lastSyncedAt;

  @override
  Widget build(BuildContext context) {
    if (state == LoadState.loading) {
      return const Semantics(
        label: '正在載入內容',
        liveRegion: true,
        child: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
          CircularProgressIndicator(),
          SizedBox(height: 12),
          Text('正在載入，請稍候'),
        ])),
      );
    }
    final (icon, title, detail) = switch (state) {
      LoadState.empty => (Icons.inbox_outlined, '目前沒有內容', '之後再回來看看'),
      LoadState.error => (Icons.error_outline, '暫時無法顯示', '請稍後重試'),
      LoadState.offline => (
          Icons.cloud_off_outlined,
          '目前為離線唯讀模式',
          '最後同步：${_formatTimestamp(lastSyncedAt)}',
        ),
      LoadState.loading => throw StateError('handled above'),
    };
    return Semantics(
      label: '$title。$detail',
      liveRegion: true,
      child: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon),
        Text(title),
        Text(detail),
      ])),
    );
  }

  static String _formatTimestamp(DateTime? value) {
    if (value == null) return '尚無同步資料';
    final utc = value.toUtc();
    String two(int number) => number.toString().padLeft(2, '0');
    return '${utc.year}-${two(utc.month)}-${two(utc.day)} ${two(utc.hour)}:${two(utc.minute)} UTC';
  }
}
