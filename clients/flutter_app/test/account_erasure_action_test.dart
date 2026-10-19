import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/integration.dart';

const owner = '11111111-1111-4111-8111-111111111111';
const job = '33333333-3333-4333-8333-333333333333';
final credential = 'a' * 80;
final nonce = 'n' * 43;
const secret = 'fictional_receipt_secret_12345678901234567890';

class Provider implements ErasureFreshProvider {
  @override
  String provider = 'google';
  int calls = 0;
  Future<String> Function() result = () async => 'fictional-assertion';
  @override
  Future<String> authenticate(String value) {
    calls++;
    expect(value, nonce);
    return result();
  }
}

class Transport implements ApiTransport {
  final paths = <String>[];
  Map<String, dynamic> challenge = {
    'challenge_credential': credential,
    'nonce': nonce,
    'provider': 'google',
    'expires_in': 300,
  };
  Future<ApiResponse> Function(String) result =
      (path) async => ApiResponse(200, {
            'id': job,
            'status': path.endsWith('/cancel') ? 'cancelled' : 'verified',
          });
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    expect(method, 'POST');
    expect(headers, isEmpty);
    expect(path, isNot(contains('?')));
    paths.add(path);
    if (path.endsWith('/challenge')) {
      expect(body,
          {'job_id': job, 'receipt_secret': secret, 'provider': 'google'});
      return ApiResponse(200, challenge);
    }
    expect(body, {
      'challenge_credential': credential,
      'provider_assertion': 'fictional-assertion',
      'confirmed': true,
    });
    return result(path);
  }
}

Matcher failure(ErasureActionFailureStage stage) => throwsA(predicate((e) =>
    e is ErasureActionFailure &&
    e.stage == stage &&
    !e.toString().contains('private')));

class FailingAttemptStore extends MemoryStore {
  @override
  Future<void> write(String key, String value) async {
    if (key.contains(':attempt:')) {
      throw StateError('fictional storage failure');
    }
    await super.write(key, value);
  }
}

class Cleanup implements ErasureLocalCleanup {
  int checks = 0;
  int clears = 0;
  void Function() check = () {};
  Future<void> Function() clear = () async {};

  @override
  void requireCurrent() {
    checks++;
    check();
  }

  @override
  Future<void> clearBeforeVerification() {
    clears++;
    return clear();
  }
}

void main() {
  late ErasureReceiptVault vault;
  late Transport transport;
  late Provider provider;
  late ValueNotifier<bool> online;
  late MemoryStore store;
  Future<ErasureReceiptActionClient> open(
          {ErasureLocalCleanup? localCleanup}) =>
      ErasureReceiptActionClient.open(vault, transport,
          isOnline: () => online.value,
          connectivity: online,
          localCleanup: localCleanup);
  setUp(() async {
    store = MemoryStore();
    vault = ErasureReceiptVault.forTesting(store, owner);
    await vault.save(ErasureReceipt.parse({
      'id': job,
      'status': 'requested',
      'receipt_secret': secret,
      'requested_at': '2035-01-01T00:00:00Z',
    }));
    transport = Transport();
    provider = Provider();
    online = ValueNotifier(true);
  });
  tearDown(() {
    vault.dispose();
    online.dispose();
  });

  test('verification clears only after fresh proof and before final POST',
      () async {
    final order = <String>[];
    final cleanup = Cleanup();
    provider.result = () async {
      order.add('fresh-proof');
      return 'fictional-assertion';
    };
    cleanup.clear = () async {
      order.add('cleanup');
      expect(await vault.actionWasSubmitted(job, ErasureReceiptAction.verify),
          isFalse);
    };
    transport.result = (_) async {
      order.add('final-post');
      return ApiResponse(200, {'id': job, 'status': 'verified'});
    };
    await (await open(localCleanup: cleanup)).execute(
        ErasureReceiptAction.verify,
        provider: provider,
        confirmed: true);
    expect(order, ['fresh-proof', 'cleanup', 'final-post']);
    expect(cleanup.clears, 1);
    expect((await vault.read())!.id, job);
  });

  test(
      'failed cleanup prevents final POST and keeps receipt without reservation',
      () async {
    final cleanup = Cleanup()
      ..clear = () async => throw StateError('fictional private cleanup');
    await expectLater(
        (await open(localCleanup: cleanup)).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        failure(ErasureActionFailureStage.beforeSubmission));
    expect(transport.paths, ['/account-erasure/receipt/challenge']);
    expect(provider.calls, 1);
    expect((await vault.read())!.id, job);
    expect(await vault.actionWasSubmitted(job, ErasureReceiptAction.verify),
        isFalse);
  });

  test('cancel does not even check stale business cleanup context', () async {
    final cleanup = Cleanup()
      ..check = () {
        throw StateError('fictional superseded business session');
      }
      ..clear = () async => throw StateError('must not clear');
    await (await open(localCleanup: cleanup)).execute(
        ErasureReceiptAction.cancel,
        provider: provider,
        confirmed: true);
    expect(cleanup.checks, 0);
    expect(cleanup.clears, 0);
    expect(transport.paths.last, '/account-erasure/cancel');
  });

  test('lost response cannot resend after reopening the durable owner vault',
      () async {
    transport.result = (_) async => throw StateError('fictional network loss');
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        failure(ErasureActionFailureStage.outcomeUnknown));
    vault.dispose();
    vault = ErasureReceiptVault.forTesting(store, owner);
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        failure(ErasureActionFailureStage.outcomeUnknown));
    expect(transport.paths.length, 2);
    expect(provider.calls, 1);
  });

  test('durable marker precedes POST and verify does not consume cancellation',
      () async {
    transport.result = (path) async {
      final action = path.endsWith('/cancel')
          ? ErasureReceiptAction.cancel
          : ErasureReceiptAction.verify;
      expect(await vault.actionWasSubmitted(job, action), isTrue);
      return ApiResponse(200, {
        'id': job,
        'status':
            action == ErasureReceiptAction.cancel ? 'cancelled' : 'verified'
      });
    };
    for (final action in ErasureReceiptAction.values) {
      await (await open()).execute(action, provider: provider, confirmed: true);
    }
    expect(transport.paths.length, 4);
    await vault.forget();
    expect(await vault.actionWasSubmitted(job, ErasureReceiptAction.verify),
        isTrue);
  });

  test('storage failure prevents final POST', () async {
    final replacement = FailingAttemptStore();
    replacement.values.addAll(store.values);
    vault.dispose();
    vault = ErasureReceiptVault.forTesting(replacement, owner);
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        failure(ErasureActionFailureStage.outcomeUnknown));
    expect(transport.paths.length, 1);
  });

  test('separate clients sharing owner vault submit only once', () async {
    final clients = [await open(), await open()];
    final results = await Future.wait(clients.map((client) async {
      try {
        await client.execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true);
        return true;
      } on ErasureActionFailure {
        return false;
      }
    }));
    expect(results.where((result) => result).length, 1);
    expect(transport.paths.where((path) => !path.endsWith('/challenge')).length,
        1);
  });

  for (final action in ErasureReceiptAction.values) {
    test('${action.name} uses distinct endpoints and keeps receipt', () async {
      final client = await open();
      await client.execute(action, provider: provider, confirmed: true);
      expect(
          transport.paths,
          action == ErasureReceiptAction.verify
              ? [
                  '/account-erasure/receipt/challenge',
                  '/account-erasure/receipt/verify'
                ]
              : [
                  '/account-erasure/cancel/challenge',
                  '/account-erasure/cancel'
                ]);
      expect(provider.calls, 1);
      expect((await vault.read())!.id, job);
      await expectLater(
          client.execute(action, provider: provider, confirmed: true),
          failure(ErasureActionFailureStage.outcomeUnknown));
      expect(transport.paths.length, 2);
    });
  }
  test('no confirmation or offline sends nothing', () async {
    for (final confirmed in [false, true]) {
      online.value = !confirmed;
      await expectLater(
          (await open()).execute(ErasureReceiptAction.verify,
              provider: provider, confirmed: confirmed),
          failure(ErasureActionFailureStage.beforeSubmission));
    }
    expect(transport.paths, isEmpty);
    expect(provider.calls, 0);
  });
  test('malformed or mismatched challenge never opens provider', () async {
    final original = Map<String, dynamic>.from(transport.challenge);
    for (final change in [
      {'provider': 'apple'},
      {'expires_in': 301},
      {'expires_in': 0},
      {'expires_in': '300'},
      {'nonce': 'short'},
      {'challenge_credential': 'short'},
      {'extra': 'private sentinel'},
    ]) {
      transport.challenge = {...original, ...change};
      await expectLater(
          (await open()).execute(ErasureReceiptAction.cancel,
              provider: provider, confirmed: true),
          failure(ErasureActionFailureStage.beforeSubmission));
    }
    expect(provider.calls, 0);
    expect(transport.paths.every((p) => p.endsWith('/challenge')), isTrue);
  });
  test('double tap while provider awaits makes one attempt', () async {
    final started = Completer<void>();
    final answer = Completer<String>();
    provider.result = () {
      started.complete();
      return answer.future;
    };
    final client = await open();
    final first = client.execute(ErasureReceiptAction.verify,
        provider: provider, confirmed: true);
    await started.future;
    await expectLater(
        client.execute(ErasureReceiptAction.cancel,
            provider: provider, confirmed: true),
        failure(ErasureActionFailureStage.beforeSubmission));
    answer.complete('fictional-assertion');
    await first;
    expect(transport.paths.length, 2);
    expect(provider.calls, 1);
  });
  test('duplicate while final POST waits preserves dispatched uncertainty',
      () async {
    final started = Completer<void>();
    final response = Completer<ApiResponse>();
    transport.result = (_) {
      started.complete();
      return response.future;
    };
    final client = await open();
    final first = client.execute(ErasureReceiptAction.verify,
        provider: provider, confirmed: true);
    final checked =
        expectLater(first, failure(ErasureActionFailureStage.outcomeUnknown));
    await started.future;
    try {
      await expectLater(
          client.execute(ErasureReceiptAction.verify,
              provider: provider, confirmed: true),
          failure(ErasureActionFailureStage.outcomeUnknown));
    } finally {
      response.complete(ApiResponse(503, null));
      await checked;
    }
    expect(transport.paths.length, 2);
  });
  for (final invalidation in ['owner', 'offline', 'receipt']) {
    test('$invalidation change during provider prevents submit', () async {
      provider.result = () async {
        if (invalidation == 'owner') vault.invalidate();
        if (invalidation == 'offline') online.value = false;
        if (invalidation == 'receipt') await vault.forget();
        return 'fictional-assertion';
      };
      await expectLater(
          (await open()).execute(ErasureReceiptAction.verify,
              provider: provider, confirmed: true),
          failure(ErasureActionFailureStage.beforeSubmission));
      expect(transport.paths.length, 1);
    });
  }
  test('provider error has fixed message and no final POST', () async {
    provider.result = () async => throw StateError('private assertion');
    await expectLater(
        (await open()).execute(ErasureReceiptAction.verify,
            provider: provider, confirmed: true),
        failure(ErasureActionFailureStage.beforeSubmission));
    expect(transport.paths.length, 1);
  });
  for (final mode in ['exception', 'http', 'body', 'owner', 'offline']) {
    test('$mode after dispatch remains unknown and never retries', () async {
      transport.result = (_) async {
        if (mode == 'exception') throw StateError('private body');
        if (mode == 'http') return ApiResponse(503, null);
        if (mode == 'body') {
          return ApiResponse(200, {'id': job, 'status': 'completed'});
        }
        if (mode == 'owner') vault.invalidate();
        if (mode == 'offline') online.value = false;
        return ApiResponse(200, {'id': job, 'status': 'verified'});
      };
      final client = await open();
      await expectLater(
          client.execute(ErasureReceiptAction.verify,
              provider: provider, confirmed: true),
          failure(ErasureActionFailureStage.outcomeUnknown));
      await expectLater(
          client.execute(ErasureReceiptAction.verify,
              provider: provider, confirmed: true),
          failure(ErasureActionFailureStage.outcomeUnknown));
      expect(transport.paths.length, 2);
      expect(provider.calls, 1);
    });
  }
}
