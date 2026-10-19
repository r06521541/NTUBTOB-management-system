import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/integration.dart';

const owner = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
const job = '33333333-3333-4333-8333-333333333333';
const secret = 'fictional_receipt_secret_12345678901234567890';
Map<String, dynamic> receipt() => {
      'id': job,
      'status': 'requested',
      'receipt_secret': secret,
      'requested_at': '2035-01-01T00:00:00Z',
    };
Map<String, dynamic> status() => {
      'id': job,
      'status': 'verified',
      'requested_at': '2035-01-01T00:00:00Z',
      'updated_at': '2035-01-01T00:01:00Z',
    };

class Transport implements ApiTransport {
  int calls = 0;
  Future<ApiResponse> Function() response =
      () async => ApiResponse(200, status());
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {}, Map<String, dynamic>? body}) {
    calls++;
    expect(method, 'POST');
    expect(path, '/account-erasure/status');
    expect(headers, isEmpty);
    expect(body, {'job_id': job, 'receipt_secret': secret});
    return response();
  }
}

class DelayedStore extends MemoryStore {
  final started = Completer<void>();
  final release = Completer<void>();
  @override
  Future<void> write(String key, String value) async {
    started.complete();
    await release.future;
    await super.write(key, value);
  }
}

class PausedReadStore extends MemoryStore {
  bool paused = false;
  final started = Completer<void>();
  final release = Completer<void>();
  @override
  Future<String?> read(String key) async {
    if (paused) {
      started.complete();
      await release.future;
    }
    return super.read(key);
  }
}

void main() {
  for (final forget in [false, true]) {
    test(
        'queued ${forget ? "forget" : "replacement"} invalidates pending HTTP immediately',
        () async {
      final store = PausedReadStore();
      final vault = ErasureReceiptVault.forTesting(store, owner);
      await vault.save(ErasureReceipt.parse(receipt()));
      final transport = Transport();
      final response = Completer<ApiResponse>();
      transport.response = () => response.future;
      final client = await ErasureReceiptStatusClient.open(vault, transport,
          isOnline: () => true, connectivity: ValueNotifier(true));
      final reading = client.read();
      store.paused = true;
      final pausedRead = vault.read();
      await store.started.future;
      final mutation =
          forget ? vault.forget() : vault.save(ErasureReceipt.parse(receipt()));
      try {
        final checked =
            expectLater(reading, throwsA(isA<ErasureReceiptUnavailable>()));
        response.complete(ApiResponse(200, status()));
        await checked;
      } finally {
        store.release.complete();
        await pausedRead;
        await mutation;
      }
    });
  }
  test('replacement invalidates old reader before storage write completes',
      () async {
    final store = DelayedStore();
    store.values['erasure-receipt:v1:$owner'] = jsonEncode(receipt());
    final vault = ErasureReceiptVault.forTesting(store, owner);
    final transport = Transport();
    final client = await ErasureReceiptStatusClient.open(vault, transport,
        isOnline: () => true, connectivity: ValueNotifier(true));
    final saving = vault.save(ErasureReceipt.parse(receipt()));
    await store.started.future;
    await expectLater(client.read(), throwsA(isA<ErasureReceiptUnavailable>()));
    expect(transport.calls, 0);
    store.release.complete();
    await saving;
  });
  test('strict receipt validation and no secret in object representation', () {
    final value = ErasureReceipt.parse(receipt());
    expect(value.toString(), isNot(contains(secret)));
    for (final change in [
      {'status': 'completed'},
      {'receipt_secret': 'short'},
      {'id': '${other}x'},
      {'requested_at': '2035-02-30T00:00:00Z'},
      {'extra': 'private'},
    ]) {
      expect(() => ErasureReceipt.parse({...receipt(), ...change}),
          throwsA(isA<ErasureReceiptUnavailable>()));
    }
  });

  test('reopen exact owner only and explicitly forget without touching others',
      () async {
    final store = MemoryStore();
    final first = ErasureReceiptVault.forTesting(store, owner);
    await first.save(ErasureReceipt.parse(receipt()));
    first.invalidate();
    expect(first.read(), throwsA(isA<ErasureReceiptUnavailable>()));
    final reopened = ErasureReceiptVault.forTesting(store, owner);
    final second = ErasureReceiptVault.forTesting(store, other);
    expect((await reopened.read())!.id, job);
    expect(await second.read(), isNull);
    await second.save(ErasureReceipt.parse(receipt()));
    await reopened.forget();
    expect(await reopened.read(), isNull);
    expect((await second.read())!.id, job);
  });

  test('failed storage and malformed persisted receipt expose fixed errors',
      () async {
    final store = MemoryStore();
    store.values['erasure-receipt:v1:$owner'] = 'private corrupt sentinel';
    final vault = ErasureReceiptVault.forTesting(store, owner);
    await expectLater(
        vault.read(),
        throwsA(predicate((e) =>
            e is ErasureReceiptUnavailable &&
            !e.toString().contains('sentinel'))));
    await vault.save(ErasureReceipt.parse(receipt()));
    expect((await vault.read())!.id, job);
  });

  test('in-flight old-owner storage cannot report success into new context',
      () async {
    final store = DelayedStore();
    final vault = ErasureReceiptVault.forTesting(store, owner);
    final saving = vault.save(ErasureReceipt.parse(receipt()));
    await store.started.future;
    vault.invalidate();
    final expectation =
        expectLater(saving, throwsA(isA<ErasureReceiptUnavailable>()));
    store.release.complete();
    await expectation;
    expect(await ErasureReceiptVault.forTesting(store, other).read(), isNull);
    // Exact old scope remains recoverable; invalidation is not a deletion claim.
    expect(
        (await ErasureReceiptVault.forTesting(store, owner).read())!.id, job);
  });

  test('receipt-only status works without session and offline sends nothing',
      () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), owner);
    await vault.save(ErasureReceipt.parse(receipt()));
    final transport = Transport();
    final connectivity = ValueNotifier(true);
    final client = await ErasureReceiptStatusClient.open(vault, transport,
        isOnline: () => connectivity.value, connectivity: connectivity);
    expect((await client.read())['status'], 'verified');
    connectivity.value = false;
    await expectLater(client.read(), throwsA(isA<OfflineReadOnlyException>()));
    expect(transport.calls, 1);
  });

  test('old response after owner change cannot be displayed', () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), owner);
    await vault.save(ErasureReceipt.parse(receipt()));
    final transport = Transport();
    final result = Completer<ApiResponse>();
    transport.response = () => result.future;
    final client = await ErasureReceiptStatusClient.open(vault, transport,
        isOnline: () => true, connectivity: ValueNotifier(true));
    final reading = client.read();
    vault.invalidate();
    final expectation =
        expectLater(reading, throwsA(isA<ErasureReceiptUnavailable>()));
    result.complete(ApiResponse(200, status()));
    await expectation;
    expect(transport.calls, 1);
  });

  test('replacement or forget invalidates captured receipt client', () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), owner);
    await vault.save(ErasureReceipt.parse(receipt()));
    final transport = Transport();
    final client = await ErasureReceiptStatusClient.open(vault, transport,
        isOnline: () => true, connectivity: ValueNotifier(true));
    await vault.forget();
    await expectLater(client.read(), throwsA(isA<ErasureReceiptUnavailable>()));
    expect(transport.calls, 0);
  });

  test('bad status, wrong job and transport failure never retry', () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), owner);
    await vault.save(ErasureReceipt.parse(receipt()));
    final transport = Transport();
    final client = await ErasureReceiptStatusClient.open(vault, transport,
        isOnline: () => true, connectivity: ValueNotifier(true));
    for (final response in [
      ApiResponse(401, null),
      ApiResponse(200, {...status(), 'id': other}),
      ApiResponse(200, {})
    ]) {
      transport.response = () async => response;
      await expectLater(
          client.read(), throwsA(isA<ErasureReceiptUnavailable>()));
    }
    transport.response = () async => throw StateError('private sentinel');
    await expectLater(client.read(), throwsA(isA<ErasureReceiptUnavailable>()));
    expect(transport.calls, 4);
  });
}
