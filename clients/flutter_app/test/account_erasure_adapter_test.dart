import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_adapter.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/integration.dart';

import 'account_erasure_action_test.dart' as fixture;

class FlowTransport implements ApiTransport {
  final paths = <String>[];
  String status = 'requested';
  bool loseRequest = false;
  bool loseVerify = false;
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    expect(method, 'POST');
    expect(headers, isEmpty);
    paths.add(path);
    if (path.endsWith('/challenge')) {
      return ApiResponse(200, {
        'provider': 'google',
        'nonce': fixture.nonce,
        'challenge_credential': fixture.credential,
        'expires_in': 300,
      });
    }
    if (path.endsWith('/request')) {
      if (loseRequest) throw StateError('fictional lost response');
      return ApiResponse(202, {
        'id': fixture.job,
        'status': 'requested',
        'receipt_secret': fixture.secret,
        'requested_at': '2035-01-01T00:00:00Z',
      });
    }
    if (path.endsWith('/status')) {
      return ApiResponse(200, {
        'id': fixture.job,
        'status': status,
        'requested_at': '2035-01-01T00:00:00Z',
        'updated_at': '2035-01-01T00:00:00Z',
      });
    }
    status = path.endsWith('/cancel') ? 'cancelled' : 'verified';
    if (loseVerify) throw StateError('fictional lost response');
    return ApiResponse(200, {'id': fixture.job, 'status': status});
  }
}

void main() {
  late MemoryStore store;
  late ErasureReceiptVault vault;
  late ValueNotifier<bool> online;
  late fixture.Provider provider;
  late FlowTransport transport;
  Future<AccountErasureAdapter> open({bool allowed = true}) =>
      AccountErasureAdapter.open(
        vault: vault,
        transport: transport,
        provider: provider,
        isOnline: () => online.value,
        connectivity: online,
        requestAllowed: allowed,
      );

  setUp(() {
    store = MemoryStore();
    vault = ErasureReceiptVault.forTesting(store, fixture.owner);
    online = ValueNotifier(true);
    provider = fixture.Provider();
    transport = FlowTransport();
  });

  test('dispose notifies owner invalidation before removing consumers',
      () async {
    final adapter = await open();
    await adapter.request(confirmed: true);
    final states = <(int, String?)>[];
    adapter.addListener(() => states.add((adapter.generation, adapter.jobId)));
    adapter.dispose();
    expect(states, [(1, null)]);
  });

  test('request status verify cancel compose without sessions or enrollment',
      () async {
    final adapter = await open();
    expect(await adapter.readStatus(), isNull);
    await adapter.request(confirmed: true);
    expect(adapter.jobId, fixture.job);
    expect(adapter.generation, 0);
    expect(adapter.outcomeUnknown, isFalse);
    expect((await adapter.readStatus())!['status'], 'requested');
    await adapter.verify(confirmed: true);
    expect((await adapter.readStatus())!['status'], 'verified');
    await adapter.cancel(confirmed: true);
    expect((await adapter.readStatus())!['status'], 'cancelled');
    await expectLater(adapter.verify(confirmed: true), throwsException);
    expect(provider.calls, 3);
    adapter.dispose();
    expect(store.values, isNotEmpty);
  });

  test('lost request survives reopening and recovery never repeats POST',
      () async {
    final adapter = await open();
    transport.loseRequest = true;
    await expectLater(adapter.request(confirmed: true), throwsException);
    expect(adapter.outcomeUnknown, isTrue);
    adapter.dispose();
    vault = ErasureReceiptVault.forTesting(store, fixture.owner);
    final reopened = await open();
    expect(reopened.outcomeUnknown, isTrue);
    expect(reopened.canRequest, isFalse);
    await reopened.recoverReceipt(confirmed: true);
    expect(await reopened.readStatus(), isNull);
    await expectLater(reopened.request(confirmed: true), throwsException);
    expect(transport.paths.length, 2);
    reopened.dispose();
  });

  test('lost verification permits status only across page/process recreation',
      () async {
    final adapter = await open();
    await adapter.request(confirmed: true);
    transport.loseVerify = true;
    await expectLater(adapter.verify(confirmed: true), throwsException);
    expect(adapter.outcomeUnknown, isTrue);
    adapter.dispose();
    vault = ErasureReceiptVault.forTesting(store, fixture.owner);
    final reopened = await open();
    expect(reopened.jobId, fixture.job);
    expect(reopened.outcomeUnknown, isTrue);
    expect((await reopened.readStatus())!['status'], 'verified');
    await expectLater(reopened.cancel(confirmed: true), throwsException);
    expect(transport.paths.where((p) => p.endsWith('/verify')).length, 1);
    reopened.dispose();
  });

  test('offline unconfirmed and capability denial do not authenticate',
      () async {
    final adapter = await open(allowed: false);
    await expectLater(adapter.request(confirmed: true), throwsException);
    await expectLater(
        adapter.recoverReceipt(confirmed: false), throwsException);
    online.value = false;
    await expectLater(adapter.readStatus(), throwsException);
    expect(provider.calls, 0);
    expect(transport.paths, isEmpty);
    adapter.dispose();
  });

  test('singleflight and owner invalidation reject paused provider results',
      () async {
    final pending = Completer<String>();
    provider.result = () => pending.future;
    final adapter = await open();
    final first = adapter.request(confirmed: true);
    final failure = expectLater(first, throwsException);
    await Future<void>.delayed(Duration.zero);
    await expectLater(adapter.request(confirmed: true), throwsException);
    vault.invalidate();
    pending.complete('fictional-assertion');
    await failure;
    expect(adapter.generation, 1);
    expect(adapter.jobId, isNull);
    expect(transport.paths, ['/account-erasure/request/challenge']);
    adapter.dispose();
  });
}
