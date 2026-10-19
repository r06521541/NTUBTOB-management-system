import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_adapter.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/account_erasure_flow.dart';
import 'package:ntubtob_portal/integration.dart';
import 'account_erasure_action_test.dart' as fixture;
import 'account_erasure_recovery_test.dart' as recovery;

class RecoveryWithStatus extends recovery.RecoveryTransport {
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {}, Map<String, dynamic>? body}) {
    if (path == '/account-erasure/status') {
      return Future.value(ApiResponse(200, {
        'id': fixture.job,
        'status': 'requested',
        'requested_at': '2035-01-01T00:00:00Z',
        'updated_at': '2035-01-01T00:00:00Z'
      }));
    }
    return super.send(method, path, headers: headers, body: body);
  }
}

void main() {
  testWidgets(
      'unknown request can recover by explicit proof without retrying mutation',
      (tester) async {
    final store = MemoryStore();
    await store.write(
        'erasure-receipt:v1:${fixture.owner}:request-attempt', 'unknown');
    final vault = ErasureReceiptVault.forTesting(store, fixture.owner);
    final transport = RecoveryWithStatus();
    final online = ValueNotifier(true);
    final provider = fixture.Provider();
    final adapter = await AccountErasureAdapter.open(
        vault: vault,
        transport: transport,
        provider: provider,
        isOnline: () => online.value,
        connectivity: online,
        requestAllowed: true,
        freshRecoveryAllowed: true);
    await tester
        .pumpWidget(MaterialApp(home: AccountErasureFlowPage(port: adapter)));
    await tester.pumpAndSettle();
    final action = find.byKey(const ValueKey('erasure-flow-freshRecover'));
    expect(action, findsOneWidget);
    expect(find.byKey(const ValueKey('erasure-flow-request')), findsNothing);
    await tester.tap(action);
    await tester.pumpAndSettle();
    expect(provider.calls, 0);
    expect(transport.paths, isEmpty);
    await tester
        .tap(find.byKey(const ValueKey('confirm-erasure-flow-freshRecover')));
    await tester.pumpAndSettle();
    expect(provider.calls, 1);
    expect(adapter.jobId, fixture.job);
    expect(adapter.outcomeUnknown, isTrue);
    expect(await vault.requestWasSubmitted(), isTrue);
    expect(transport.paths,
        ['/account-erasure/recovery/challenge', '/account-erasure/recovery']);
    expect(find.byKey(const ValueKey('erasure-flow-verify')), findsNothing);
    await tester.pumpWidget(const SizedBox());
    adapter.dispose();
    vault.dispose();
    final reopenedVault = ErasureReceiptVault.forTesting(store, fixture.owner);
    final reopened = await AccountErasureAdapter.open(
        vault: reopenedVault,
        transport: transport,
        provider: provider,
        isOnline: () => true,
        connectivity: online,
        requestAllowed: true,
        freshRecoveryAllowed: true);
    expect(reopened.outcomeUnknown, isTrue);
    await tester
        .pumpWidget(MaterialApp(home: AccountErasureFlowPage(port: reopened)));
    await tester.pumpAndSettle();
    expect(find.text('申請已記錄，尚待身分驗證；不表示資料已刪除。'), findsOneWidget);
    expect(find.byKey(const ValueKey('erasure-flow-verify')), findsNothing);
    expect(find.byKey(const ValueKey('erasure-flow-cancel')), findsNothing);
    expect(provider.calls, 1);
    await tester.pumpWidget(const SizedBox());
    reopened.dispose();
    reopenedVault.dispose();
    online.dispose();
  });

  testWidgets('fresh recovery is default off', (tester) async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
    final online = ValueNotifier(true);
    final adapter = await AccountErasureAdapter.open(
        vault: vault,
        transport: recovery.RecoveryTransport(),
        provider: fixture.Provider(),
        isOnline: () => true,
        connectivity: online,
        requestAllowed: false);
    await tester
        .pumpWidget(MaterialApp(home: AccountErasureFlowPage(port: adapter)));
    await tester.pumpAndSettle();
    expect(
        find.byKey(const ValueKey('erasure-flow-freshRecover')), findsNothing);
    await tester.pumpWidget(const SizedBox());
    adapter.dispose();
    vault.dispose();
    online.dispose();
  });
}
