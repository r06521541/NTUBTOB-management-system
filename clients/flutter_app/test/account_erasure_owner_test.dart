import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/account_erasure_flow.dart';
import 'package:ntubtob_portal/account_erasure_owner.dart';
import 'package:ntubtob_portal/support_app_info.dart';
import 'package:ntubtob_portal/integration.dart';

import 'account_erasure_action_test.dart' as fixture;
import 'account_erasure_local_cleanup_test.dart' as cleanup_fixture;
import 'account_erasure_provider_test.dart' as provider_fixture;

const ownerKey = 'erasure-owner:v1';

class FixedIds extends SecureIds {
  @override
  String next() => 'A' * 43;
}

class OwnerStore extends MemoryStore {
  int reads = 0;
  int writes = 0;
  bool failWrite = false;
  Completer<void>? entered;
  Completer<void>? release;
  Completer<void>? receiptEntered;
  Completer<void>? receiptRelease;

  @override
  Future<String?> read(String key) async {
    reads++;
    return super.read(key);
  }

  @override
  Future<void> write(String key, String value) async {
    writes++;
    if (key.startsWith('erasure-receipt:v1:') &&
        key.split(':').length == 3 &&
        receiptRelease != null) {
      receiptEntered!.complete();
      await receiptRelease!.future;
    }
    if (key == ownerKey) {
      if (failWrite) throw StateError('fictional private store error');
      if (release != null) {
        entered!.complete();
        await release!.future;
      }
    }
    await super.write(key, value);
  }
}

class OwnerTransport implements ApiTransport {
  final paths = <String>[];
  String provider = 'apple';
  String status = 'requested';
  bool loseRequest = false;
  Completer<void>? statusEntered;
  Completer<ApiResponse>? pendingStatus;

  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    expect(method, 'POST');
    expect(headers, isEmpty);
    paths.add(path);
    if (path.endsWith('/challenge')) {
      provider = body!['provider'] as String;
      return ApiResponse(200, {
        'provider': provider,
        'nonce': fixture.nonce,
        'challenge_credential': fixture.credential,
        'expires_in': 300,
      });
    }
    if (path.endsWith('/request')) {
      if (loseRequest) throw StateError('fictional lost reply');
      return ApiResponse(202, {
        'id': fixture.job,
        'status': 'requested',
        'receipt_secret': fixture.secret,
        'requested_at': '2035-01-01T00:00:00Z',
      });
    }
    if (path.endsWith('/status')) {
      if (pendingStatus != null) {
        statusEntered!.complete();
        return pendingStatus!.future;
      }
      return statusResponse();
    }
    status = path.endsWith('/cancel') ? 'cancelled' : 'verified';
    return ApiResponse(200, {'id': fixture.job, 'status': status});
  }

  ApiResponse statusResponse() => ApiResponse(200, {
        'id': fixture.job,
        'status': status,
        'requested_at': '2035-01-01T00:00:00Z',
        'updated_at': '2035-01-01T00:00:00Z',
      });
}

void main() {
  late OwnerStore store;
  late OwnerTransport transport;
  late provider_fixture.ProofPorts ports;
  late ValueNotifier<bool> online;
  late SessionController session;
  late int purges;

  AccountErasureOwner owner({SessionController? boundSession}) {
    final result = AccountErasureOwner(
      store: store,
      session: boundSession ?? session,
      transport: transport,
      isOnline: () => online.value,
      connectivity: online,
      apple: ports,
      line: ports,
      ids: FixedIds(),
    );
    addTearDown(result.dispose);
    return result;
  }

  setUp(() {
    store = OwnerStore();
    transport = OwnerTransport();
    ports = provider_fixture.ProofPorts();
    online = ValueNotifier(true);
    purges = 0;
    session = SessionController(transport, store, 'fixture', SecureIds(),
        terminalPurge: () async {
      purges++;
      await store.deleteKeysWithPrefix('fictional-private:');
    });
    addTearDown(online.dispose);
  });

  test('construction is unused; Google and unconfirmed open touch nothing',
      () async {
    final controller = owner();
    expect(controller.flow, isNull);
    expect(store.reads, 0);
    expect(store.writes, 0);
    await expectLater(controller.start(provider: 'google', confirmed: true),
        throwsA(isA<ErasureReceiptUnavailable>()));
    await expectLater(controller.start(provider: 'apple', confirmed: false),
        throwsA(isA<ErasureReceiptUnavailable>()));
    await expectLater(controller.resume(confirmed: false), throwsException);
    expect(store.reads, 0);
    expect(store.writes, 0);
    expect(ports.nonces, isEmpty);
    expect(transport.paths, isEmpty);
  });

  for (final provider in ['apple', 'line']) {
    test('$provider owns one opaque persisted scope and uses nonce-only proof',
        () async {
      final controller = owner();
      final flow = await controller.start(provider: provider, confirmed: true);
      expect(identical(controller.flow, flow), isTrue);
      expect(flow.canRequest, isTrue);
      expect(transport.paths, isEmpty);
      final record = jsonDecode(store.values[ownerKey]!) as Map;
      expect(record.keys.toSet(), {'version', 'scope', 'provider'});
      expect(record['version'], 1);
      expect(record['provider'], provider);
      expect(record['scope'], '00000000-0000-4000-8000-000000000000');
      await flow.request(confirmed: true);
      expect(flow.jobId, fixture.job);
      expect(ports.nonces, [fixture.nonce]);
      expect(ports.logoutCalls, 0);
      expect(ports.envelopeCalls, 0);
      expect(store.values.keys.where((k) => k.startsWith('erasure-receipt:')),
          hasLength(2));
      final before = Map<String, String>.of(store.values);
      await expectLater(controller.start(provider: provider, confirmed: true),
          throwsException);
      await expectLater(owner().resume(confirmed: true), throwsException);
      expect(store.values, before);
      expect(transport.paths,
          ['/account-erasure/request/challenge', '/account-erasure/request']);
    });
  }

  test('own verification purge preserves receipt and later cancellation proof',
      () async {
    await session.accept(cleanup_fixture.sessionEnvelope('original'));
    store.values['fictional-private:original'] = 'fictional private cache';
    final controller = owner();
    final flow = await controller.start(provider: 'apple', confirmed: true);
    await flow.request(confirmed: true);
    final beforeGeneration = session.generation;
    await flow.verify(confirmed: true);
    expect(session.generation, beforeGeneration + 1);
    expect(session.accessToken, isNull);
    expect(store.values.containsKey('refresh:fixture'), isFalse);
    expect(store.values.containsKey('fictional-private:original'), isFalse);
    expect(purges, 1);
    controller.requireCurrent();
    flow.requireCurrent();
    expect(flow.jobId, fixture.job);
    expect((await flow.readStatus())!['status'], 'verified');
    await flow.cancel(confirmed: true);
    expect(purges, 1);
    expect(ports.nonces, [fixture.nonce, fixture.nonce, fixture.nonce]);
    expect(transport.paths.any((path) => path.startsWith('/auth/')), isFalse);
  });

  test('restart requires explicit signed-out resume and never repeats unknown',
      () async {
    var controller = owner();
    final first = await controller.start(provider: 'line', confirmed: true);
    transport.loseRequest = true;
    await expectLater(first.request(confirmed: true), throwsException);
    expect(first.outcomeUnknown, isTrue);
    final saved = store.values[ownerKey];
    controller.dispose();
    controller = owner();
    expect(controller.flow, isNull);
    final beforeCalls = transport.paths.length;
    final resumed = await controller.resume(confirmed: true);
    expect(store.values[ownerKey], saved);
    expect(resumed.canRequest, isFalse);
    expect(resumed.outcomeUnknown, isTrue);
    expect(
        resumed,
        isA<AccountErasureFreshRecoveryPort>().having(
            (port) => port.canRecoverWithProof, 'fresh recovery', isTrue));
    await resumed.recoverReceipt(confirmed: true);
    expect(await resumed.readStatus(), isNull);
    await expectLater(resumed.request(confirmed: true), throwsException);
    expect(transport.paths.length, beforeCalls);
  });

  test('new session invalidates and cannot rebind a retained old scope',
      () async {
    final controller = owner();
    final flow = await controller.start(provider: 'apple', confirmed: true);
    await flow.request(confirmed: true);
    final saved = Map<String, String>.of(store.values);
    final states = <(int, String?)>[];
    flow.changes.addListener(() => states.add((flow.generation, flow.jobId)));
    await session.accept(cleanup_fixture.sessionEnvelope('different'));
    expect(controller.flow, isNull);
    expect(() => flow.requireCurrent(), throwsException);
    expect(states, [(1, null)]);
    final latest = owner();
    await expectLater(latest.resume(confirmed: true), throwsException);
    await expectLater(
        latest.start(provider: 'line', confirmed: true), throwsException);
    for (final entry in saved.entries) {
      expect(store.values[entry.key], entry.value);
    }
  });

  test('new owner during provider prompt cannot submit or clear new session',
      () async {
    final controller = owner();
    final flow = await controller.start(provider: 'apple', confirmed: true);
    final entered = Completer<void>();
    final answer = Completer<String>();
    ports.result = () {
      entered.complete();
      return answer.future;
    };
    final result = expectLater(flow.request(confirmed: true), throwsException);
    await entered.future;
    await session.accept(cleanup_fixture.sessionEnvelope('different'));
    answer.complete('fictional-proof');
    await result;
    expect(transport.paths, ['/account-erasure/request/challenge']);
    expect(session.accessToken,
        cleanup_fixture.sessionEnvelope('different').accessToken);
    expect(purges, 0);
  });

  test('reentrant login during intentional purge is not mistaken for exemption',
      () async {
    final controller = owner();
    final flow = await controller.start(provider: 'apple', confirmed: true);
    await flow.request(confirmed: true);
    Future<void>? accepted;
    void replace() {
      if (session.generation == 1) {
        accepted = session.accept(cleanup_fixture.sessionEnvelope('different'));
      }
    }

    session.generationChanges.addListener(replace);
    try {
      await expectLater(flow.verify(confirmed: true), throwsException);
      await accepted;
    } finally {
      session.generationChanges.removeListener(replace);
    }
    expect(controller.flow, isNull);
    expect(transport.paths.where((p) => p.endsWith('/verify')), isEmpty);
    expect(session.accessToken,
        cleanup_fixture.sessionEnvelope('different').accessToken);
  });

  test('singleflight persist cannot race a second controller or owner switch',
      () async {
    store.entered = Completer<void>();
    store.release = Completer<void>();
    final first = owner();
    final second = owner();
    final opening = first.start(provider: 'apple', confirmed: true);
    final rejected = expectLater(opening, throwsException);
    await store.entered!.future;
    await expectLater(
        first.start(provider: 'line', confirmed: true), throwsException);
    await expectLater(
        second.start(provider: 'line', confirmed: true), throwsException);
    first.dispose();
    await expectLater(second.resume(confirmed: true), throwsException);
    store.release!.complete();
    await rejected;
    expect(first.flow, isNull);
    expect(store.writes, 1);
    expect(transport.paths, isEmpty);
  });

  test('corrupt or missing record and unavailable storage fail without rewrite',
      () async {
    final controller = owner();
    await expectLater(controller.resume(confirmed: true), throwsException);
    for (final raw in ['private invalid data', '{}', 'x' * 513]) {
      store.values[ownerKey] = raw;
      await expectLater(controller.resume(confirmed: true), throwsException);
      await expectLater(controller.start(provider: 'apple', confirmed: true),
          throwsException);
      expect(store.values[ownerKey], raw);
    }
    store.values.remove(ownerKey);
    store.failWrite = true;
    await expectLater(controller.start(provider: 'apple', confirmed: true),
        throwsA(isA<ErasureReceiptUnavailable>()));
    expect(controller.flow, isNull);
    expect(ports.nonces, isEmpty);
    expect(transport.paths, isEmpty);
  });

  test('disposed owner retains lease until its pending receipt write settles',
      () async {
    final first = owner();
    final flow = await first.start(provider: 'apple', confirmed: true);
    store.receiptEntered = Completer<void>();
    store.receiptRelease = Completer<void>();
    final result = expectLater(flow.request(confirmed: true), throwsException);
    await store.receiptEntered!.future;
    first.dispose();
    final second = owner();
    try {
      await expectLater(second.resume(confirmed: true), throwsException);
      expect(second.flow, isNull);
    } finally {
      store.receiptRelease!.complete();
      await result;
    }
    final resumed = await second.resume(confirmed: true);
    expect(resumed.jobId, fixture.job);
    expect(resumed.canRequest, isFalse);
    expect(transport.paths.where((p) => p.endsWith('/request')), hasLength(1));
  });

  test('resume refuses ambiguous refresh state without provider or overwrite',
      () async {
    final first = owner();
    await first.start(provider: 'apple', confirmed: true);
    first.dispose();
    store.values['refresh-attempt:fixture'] = 'fictional uncertain refresh';
    final saved = Map<String, String>.of(store.values);
    await expectLater(owner().resume(confirmed: true), throwsException);
    expect(store.values, saved);
    expect(ports.nonces, isEmpty);
    expect(transport.paths, isEmpty);
  });

  test('late status and disposal cannot expose receipt in another owner',
      () async {
    final controller = owner();
    final flow = await controller.start(provider: 'apple', confirmed: true);
    await flow.request(confirmed: true);
    transport.pendingStatus = Completer<ApiResponse>();
    transport.statusEntered = Completer<void>();
    final pending = expectLater(flow.readStatus(), throwsException);
    await transport.statusEntered!.future;
    controller.dispose();
    transport.pendingStatus!.complete(transport.statusResponse());
    await pending;
    expect(flow.jobId, isNull);
    expect(store.values[ownerKey], isNotNull);
  });

  testWidgets(
      'owned flow renders through support builder without native enablement',
      (tester) async {
    online.value = false;
    store.values['installation:v1'] = 'fictional-install';
    final controller = owner();
    final flow = await controller.start(provider: 'apple', confirmed: true);
    await tester.pumpWidget(MaterialApp(
      home: SupportAppInfoPage(
        erasureEntryBuilder: (_) => AccountErasureFlowPage(port: flow),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('account-erasure-flow-entry')));
    await tester.pumpAndSettle();
    expect(find.byType(AccountErasureFlowPage), findsOneWidget);
    expect(find.textContaining(fixture.secret), findsNothing);
    expect(transport.paths, isEmpty);
    expect(ports.nonces, isEmpty);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
