import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_adapter.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/account_erasure_local_cleanup.dart';
import 'package:ntubtob_portal/integration.dart';

import 'account_erasure_action_test.dart' as fixture;
import 'account_erasure_adapter_test.dart' as adapter_fixture;

const personalPrefixes = [
  'cache:v1:fixture:',
  'notification-cache:v1:fixture:',
  'officer-report-cache:v1:fixture:',
  'mutation:fixture:',
  'event-mutation:fixture:',
  'profile-mutation:fixture:',
];

SessionEnvelope sessionEnvelope(String account) => SessionEnvelope(
      accessToken: 'fictional-access-$account',
      refreshToken: 'fictional-refresh-$account-with-at-least-32-characters',
      sessionId: 'fictional-session-$account',
      expiresIn: 900,
    );

class AttemptStore extends MemoryStore {
  Completer<void>? reservationEntered;
  Completer<void>? reservationRelease;

  @override
  Future<void> write(String key, String value) async {
    if (key.contains(':attempt:') && reservationRelease != null) {
      reservationEntered!.complete();
      await reservationRelease!.future;
    }
    await super.write(key, value);
  }
}

void main() {
  late AttemptStore store;
  late SessionController session;
  late ErasureReceiptVault vault;
  late ValueNotifier<bool> online;
  late fixture.Provider provider;
  late fixture.Transport transport;
  late SessionBoundErasureCleanup cleanup;
  late Future<void> Function() purge;
  late int purges;

  Future<ErasureReceiptActionClient> open() =>
      ErasureReceiptActionClient.open(vault, transport,
          isOnline: () => online.value,
          connectivity: online,
          localCleanup: cleanup);

  void expectPersonal(String account, bool present) {
    for (final prefix in personalPrefixes) {
      expect(store.values.containsKey('$prefix$account'), present,
          reason: '$prefix$account');
    }
  }

  void seedPersonal(String account) {
    for (final prefix in personalPrefixes) {
      store.values['$prefix$account'] = 'fictional-personal-$account';
    }
  }

  setUp(() async {
    store = AttemptStore();
    transport = fixture.Transport();
    online = ValueNotifier(true);
    provider = fixture.Provider();
    purges = 0;
    purge = () async {
      for (final prefix in personalPrefixes) {
        await store.deleteKeysWithPrefix(prefix);
      }
    };
    session = SessionController(transport, store, 'fixture', SecureIds(),
        terminalPurge: () async {
      purges++;
      await purge();
    });
    await session.accept(sessionEnvelope('a'));
    seedPersonal('a');
    vault = ErasureReceiptVault.forTesting(store, fixture.owner);
    await vault.save(ErasureReceipt.parse({
      'id': fixture.job,
      'status': 'requested',
      'receipt_secret': fixture.secret,
      'requested_at': '2035-01-01T00:00:00Z',
    }));
    cleanup = SessionBoundErasureCleanup(session);
  });

  tearDown(() {
    vault.dispose();
    online.dispose();
  });

  test(
      'real session barrier purges personal stores and retains receipt markers',
      () async {
    final generation = session.generation;
    transport.result = (_) async {
      expect(session.generation, generation + 1);
      expect(session.accessToken, isNull);
      expect(store.values.containsKey('refresh:fixture'), isFalse);
      expectPersonal('a', false);
      expect((await vault.read())!.id, fixture.job);
      expect(
          await vault.actionWasSubmitted(
              fixture.job, ErasureReceiptAction.verify),
          isTrue);
      return ApiResponse(200, {'id': fixture.job, 'status': 'verified'});
    };
    await (await open()).execute(ErasureReceiptAction.verify,
        provider: provider, confirmed: true);
    expect(purges, 1);
    cleanup.requireCurrent();
    await cleanup.clearBeforeVerification();
    expect(purges, 1);
    expect(transport.paths, [
      '/account-erasure/receipt/challenge',
      '/account-erasure/receipt/verify'
    ]);
  });

  test('adapter forwards optional cleanup without invalidating receipt owner',
      () async {
    final adapter = await AccountErasureAdapter.open(
      vault: vault,
      transport: adapter_fixture.FlowTransport(),
      provider: provider,
      isOnline: () => online.value,
      connectivity: online,
      requestAllowed: false,
      localCleanup: cleanup,
    );
    addTearDown(adapter.dispose);
    await adapter.verify(confirmed: true);
    expect(purges, 1);
    expectPersonal('a', false);
    expect(adapter.generation, 0);
    expect(adapter.jobId, fixture.job);
    expect((await adapter.readStatus())!['status'], 'verified');
  });

  test('provider cancellation does not clear business credentials or caches',
      () async {
    provider.result = () async => throw StateError('fictional cancelled proof');
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        fixture.failure(ErasureActionFailureStage.beforeSubmission));
    expect(purges, 0);
    expectPersonal('a', true);
    expect(session.accessToken, sessionEnvelope('a').accessToken);
  });

  test('cleanup failure keeps debt and receipt and cannot publish or POST',
      () async {
    purge = () async => throw StateError('fictional private cleanup failure');
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        fixture.failure(ErasureActionFailureStage.beforeSubmission));
    expect(transport.paths, ['/account-erasure/receipt/challenge']);
    expect(store.values['session-cleanup-pending:fixture'], 'true');
    expect((await vault.read())!.id, fixture.job);
    expect(session.accessToken, isNull);
    await expectLater(session.accept(sessionEnvelope('b')), throwsStateError);
    expect(session.accessToken, isNull);
    expect(purges, 1);
    expect(() => cleanup.requireCurrent(), throwsException);
  });

  test('new login during provider proof is rejected before cleanup', () async {
    final entered = Completer<void>();
    final answer = Completer<String>();
    provider.result = () {
      entered.complete();
      return answer.future;
    };
    final action = (await open()).execute(ErasureReceiptAction.verify,
        provider: provider, confirmed: true);
    final checked = expectLater(
        action, fixture.failure(ErasureActionFailureStage.beforeSubmission));
    await entered.future;
    await session.accept(sessionEnvelope('b'));
    seedPersonal('b');
    final priorPurges = purges;
    answer.complete('fictional-assertion');
    await checked;
    expect(purges, priorPurges);
    expectPersonal('b', true);
    expect(session.accessToken, sessionEnvelope('b').accessToken);
    expect(transport.paths, ['/account-erasure/receipt/challenge']);
  });

  test('new login during paused cleanup survives but old verification stops',
      () async {
    final entered = Completer<void>();
    final release = Completer<void>();
    final originalPurge = purge;
    purge = () async {
      entered.complete();
      await release.future;
      await originalPurge();
    };
    final action = (await open()).execute(ErasureReceiptAction.verify,
        provider: provider, confirmed: true);
    final checked = expectLater(
        action, fixture.failure(ErasureActionFailureStage.beforeSubmission));
    await entered.future;
    final accepted = session.accept(sessionEnvelope('b'));
    release.complete();
    await checked;
    await accepted;
    seedPersonal('b');
    expectPersonal('a', false);
    expectPersonal('b', true);
    expect(purges, 1);
    expect(session.accessToken, sessionEnvelope('b').accessToken);
    expect(transport.paths, ['/account-erasure/receipt/challenge']);
    expect((await vault.read())!.id, fixture.job);
  });

  test('lost final response preserves receipt and never cleans or posts twice',
      () async {
    transport.result =
        (_) async => throw StateError('fictional transport loss');
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        fixture.failure(ErasureActionFailureStage.outcomeUnknown));
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        fixture.failure(ErasureActionFailureStage.outcomeUnknown));
    expect(purges, 1);
    expect(transport.paths.length, 2);
    expect((await vault.read())!.id, fixture.job);
  });

  test('new owner while reservation waits cannot pass post-cleanup checkpoint',
      () async {
    store.reservationEntered = Completer<void>();
    store.reservationRelease = Completer<void>();
    final action = (await open()).execute(ErasureReceiptAction.verify,
        provider: provider, confirmed: true);
    final checked = expectLater(
        action, fixture.failure(ErasureActionFailureStage.outcomeUnknown));
    await store.reservationEntered!.future;
    try {
      await session.accept(sessionEnvelope('b'));
      seedPersonal('b');
    } finally {
      store.reservationRelease!.complete();
    }
    await checked;
    expect(purges, 1);
    expectPersonal('b', true);
    expect(session.accessToken, sessionEnvelope('b').accessToken);
    expect(transport.paths, ['/account-erasure/receipt/challenge']);
    expect((await vault.read())!.id, fixture.job);
    // An existing durable unknown marker wins even when business ownership is
    // stale. It is not reclassified as permission to send another attempt.
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        fixture.failure(ErasureActionFailureStage.outcomeUnknown));
    expect(transport.paths.length, 1);
  });

  test('generation observer reentry joins the same cleanup barrier', () async {
    final originalGeneration = session.generation;
    Future<void>? observed;
    void listener() {
      if (session.generation == originalGeneration + 1) {
        observed = cleanup.clearBeforeVerification();
      }
    }

    session.generationChanges.addListener(listener);
    try {
      await cleanup.clearBeforeVerification();
      await observed;
    } finally {
      session.generationChanges.removeListener(listener);
    }
    expect(purges, 1);
    expectPersonal('a', false);
  });

  test('cleanup cannot claim personal purge without configured terminal hook',
      () {
    final unconfigured =
        SessionController(transport, store, 'other', SecureIds());
    expect(() => SessionBoundErasureCleanup(unconfigured), throwsException);
  });
}
