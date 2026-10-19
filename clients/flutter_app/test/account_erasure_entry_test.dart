import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_entry.dart';
import 'package:ntubtob_portal/account_erasure_flow.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/local_preferences.dart';
import 'package:ntubtob_portal/support_app_info.dart';

class OfflineFlow extends ChangeNotifier implements AccountErasureFlowPort {
  int calls = 0;
  @override
  Listenable get changes => this;
  @override
  bool get online => false;
  @override
  int get generation => 0;
  @override
  bool get canRequest => true;
  @override
  bool get outcomeUnknown => false;
  @override
  String? get jobId => null;
  @override
  void requireCurrent() {}
  @override
  Future<Map<String, dynamic>?> readStatus() async {
    calls++;
    return null;
  }

  @override
  Future<void> request({required bool confirmed}) async {
    calls++;
  }

  @override
  Future<void> verify({required bool confirmed}) async {
    calls++;
  }

  @override
  Future<void> cancel({required bool confirmed}) async {
    calls++;
  }

  @override
  Future<void> recoverReceipt({required bool confirmed}) async {
    calls++;
  }
}

void main() {
  for (final onboarded in [false, true]) {
    testWidgets(
        'receipt entry reachable without business login, onboarding=$onboarded',
        (tester) async {
      final store = MemoryStore();
      await store.write('installation:v1', 'fictional-install');
      if (onboarded) {
        await LocalPreferences(store, 'fictional-install').completeOnboarding();
      }
      final online = ValueNotifier(false);
      addTearDown(online.dispose);
      await tester.pumpWidget(BasicBootstrapApp(
        config: AppConfig.parse(
            flavor: 'staging',
            mode: 'real',
            apiBaseUrl: 'https://example.invalid/api/v1',
            lineChannelId: '1234567890',
            googleClientId: 'fixture-ios.apps.googleusercontent.com',
            googleServerClientId: 'fixture-web.apps.googleusercontent.com'),
        store: store,
        erasureEntry: AccountErasureEntryOptions(
          isOnline: () => online.value,
          connectivity: online,
        ),
      ));
      await tester.pumpAndSettle();
      final before = Map<String, String>.of(store.values);
      await tester.tap(find.byTooltip('支援與 App 資訊'));
      await tester.pumpAndSettle();
      await tester
          .tap(find.byKey(const ValueKey('account-erasure-flow-entry')));
      await tester.pumpAndSettle();
      expect(find.byType(AccountErasureEntryPage), findsOneWidget);
      expect(find.byType(AccountErasureFlowPage), findsNothing);
      expect(store.values, before);
      expect(tester.takeException(), isNull);
    });
  }
  testWidgets(
      'explicit erasure entry opens flow without contacting server offline',
      (tester) async {
    final flow = OfflineFlow();
    addTearDown(flow.dispose);
    await tester.pumpWidget(MaterialApp(
      home: SupportAppInfoPage(
        erasureEntryBuilder: (_) => AccountErasureFlowPage(port: flow),
      ),
    ));
    expect(find.textContaining('既有球隊聯絡管道'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('account-erasure-flow-entry')));
    await tester.pumpAndSettle();
    expect(find.byType(AccountErasureFlowPage), findsOneWidget);
    expect(flow.calls, 0);
  });
}
