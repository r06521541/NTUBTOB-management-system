import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_adapter.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/account_erasure_flow.dart';
import 'package:ntubtob_portal/account_erasure_local_cleanup.dart';
import 'package:ntubtob_portal/account_erasure_status.dart';
import 'package:ntubtob_portal/integration.dart';

import 'account_erasure_action_test.dart' as action_fixture;
import 'account_erasure_adapter_test.dart' as adapter_fixture;
import 'account_erasure_local_cleanup_test.dart' as cleanup_fixture;

Finder button(String name) => find.byKey(ValueKey('erasure-flow-$name'));

Future<void> confirm(WidgetTester tester, String name) async {
  await tester.tap(button(name));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(ValueKey('confirm-erasure-flow-$name')));
  await tester.pumpAndSettle();
}

void main() {
  for (final lost in [false, true]) {
    testWidgets('real adapter UI survives local purge and reopen; lost=$lost',
        (tester) async {
      final store = MemoryStore();
      final online = ValueNotifier(true);
      final transport = adapter_fixture.FlowTransport();
      final provider = action_fixture.Provider();
      var purges = 0;
      final session = SessionController(
          transport, store, 'fixture', SecureIds(), terminalPurge: () async {
        purges++;
        await store.deleteKeysWithPrefix('fictional-private-cache:');
      });
      await session.accept(cleanup_fixture.sessionEnvelope('a'));
      store.values['refresh-attempt:fixture'] = 'fictional-existing-attempt';
      store.values['fictional-private-cache:a'] = 'fictional-personal-data';
      var vault = ErasureReceiptVault.forTesting(store, action_fixture.owner);
      Future<AccountErasureAdapter> open() => AccountErasureAdapter.open(
            vault: vault,
            transport: transport,
            provider: provider,
            isOnline: () => online.value,
            connectivity: online,
            requestAllowed: true,
            localCleanup: SessionBoundErasureCleanup(session),
          );
      var adapter = await open();
      await tester
          .pumpWidget(MaterialApp(home: AccountErasureFlowPage(port: adapter)));
      await tester.pumpAndSettle();
      expect(transport.paths, isEmpty);
      await confirm(tester, 'request');
      expect(purges, 0);
      await tester.tap(button('status'));
      await tester.pumpAndSettle();
      expect(find.text(AccountErasureStatus.messages['requested']!),
          findsOneWidget);
      transport.loseVerify = lost;
      final originalGeneration = session.generation;
      await confirm(tester, 'verify');
      expect(purges, 1);
      expect(session.generation, originalGeneration + 1);
      expect(session.accessToken, isNull);
      expect(store.values.containsKey('refresh:fixture'), isFalse);
      expect(store.values.containsKey('refresh-attempt:fixture'), isFalse);
      expect(store.values.containsKey('fictional-private-cache:a'), isFalse);
      expect(await vault.read(), isNotNull);
      expect(transport.paths.where((p) => p.endsWith('/verify')).length, 1);

      await tester.pumpWidget(const SizedBox());
      adapter.dispose();
      vault = ErasureReceiptVault.forTesting(store, action_fixture.owner);
      adapter = await open();
      await tester
          .pumpWidget(MaterialApp(home: AccountErasureFlowPage(port: adapter)));
      await tester.pumpAndSettle();
      expect(find.text(AccountErasureStatus.messages['verified']!),
          findsOneWidget);
      expect(button('verify'), findsNothing);
      expect(button('request'), findsNothing);
      expect(button('cancel'), findsNothing);
      expect(provider.calls, 2);
      expect(purges, 1);

      transport.status = 'online_completed';
      await tester.tap(button('status'));
      await tester.pumpAndSettle();
      expect(find.text(AccountErasureStatus.messages['online_completed']!),
          findsOneWidget);
      expect(find.textContaining('整體刪除流程尚未完成'), findsOneWidget);
      expect(
          find.text(AccountErasureStatus.messages['completed']!), findsNothing);
      expect(find.textContaining(action_fixture.secret), findsNothing);
      expect(transport.paths.where((p) => p.endsWith('/verify')).length, 1);
      expect(transport.paths.every((p) => p.startsWith('/account-erasure/')),
          isTrue);
      await tester.pumpWidget(const SizedBox());
      adapter.dispose();
      online.dispose();
    });
  }
}
