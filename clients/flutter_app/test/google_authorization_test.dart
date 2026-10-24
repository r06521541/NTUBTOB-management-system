import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_owner.dart';
import 'package:ntubtob_portal/google_authorization.dart';
import 'package:ntubtob_portal/integration.dart';

import 'account_erasure_owner_test.dart' as owner_fixture;
import 'account_erasure_provider_test.dart' as provider_fixture;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('fictional/google-authorization');
  const client = 'fictional-ios.apps.googleusercontent.com';
  const server = 'fictional-server.apps.googleusercontent.com';
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final nonce = 'n' * 43;
  final rejected = throwsA(isA<GoogleAuthorizationUnavailable>());
  void current() {}
  late List<String> order;
  late List<MethodCall> calls;
  late Future<Object?> Function() response;

  Future<void> initialize(
      {String? clientId, required String serverClientId}) async {
    expect(serverClientId, server);
    order.add('initialize:${clientId ?? 'android'}');
  }

  NativeGoogleAuthorization port(
          {String platform = 'ios',
          String clientId = client,
          String serverClientId = server}) =>
      NativeGoogleAuthorization.forTesting(platform, clientId, serverClientId,
          channel: channel, initialize: initialize);

  setUp(() {
    GoogleSignInProcessInitializer.resetForTest();
    order = [];
    calls = [];
    response = () async => {'identity_token': 'fictional.payload.signature'};
    messenger.setMockMethodCallHandler(channel, (call) async {
      order.add('authorize');
      calls.add(call);
      return response();
    });
  });
  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  test(
      'first provider use initializes without nonce then passes each fresh nonce',
      () async {
    final google = port();
    expect(order, isEmpty);
    expect(await google.authorize(nonce, beforePrompt: current),
        'fictional.payload.signature');
    expect(await google.authorize('b' * 43, beforePrompt: current),
        'fictional.payload.signature');
    expect(order, ['initialize:$client', 'authorize', 'authorize']);
    expect(calls.map((c) => c.method), ['authorize', 'authorize']);
    expect(calls[0].arguments, {
      'raw_nonce': nonce,
      'client_id': client,
      'server_client_id': server,
    });
    expect(calls[1].arguments['raw_nonce'], 'b' * 43);
  });

  test('Android uses server audience and not the iOS client in initializer',
      () async {
    for (final unusedClient in ['', 'unused-android-client', server, client]) {
      await port(platform: 'android', clientId: unusedClient)
          .authorize(nonce, beforePrompt: current);
    }
    expect(order, [
      'initialize:android',
      'authorize',
      'authorize',
      'authorize',
      'authorize'
    ]);
    for (final call in calls) {
      expect(call.arguments['server_client_id'], server);
      expect(call.arguments['client_id'], '');
    }
  });

  test(
      'invalid nonce or unsupported platform never invokes initialization or bridge',
      () async {
    for (final bad in [
      '',
      'n' * 42,
      'n' * 44,
      '${'n' * 42}\n',
      '${'n' * 42}é'
    ]) {
      await expectLater(port().authorize(bad, beforePrompt: current), rejected);
    }
    await expectLater(
        port(platform: 'web').authorize(nonce, beforePrompt: current),
        rejected);
    expect(order, isEmpty);
  });

  test('mismatched process configuration never reinitializes or opens prompt',
      () async {
    await port().authorize(nonce, beforePrompt: current);
    final baseline = List<String>.of(order);
    await expectLater(
        port(serverClientId: 'different-server.apps.googleusercontent.com')
            .authorize(nonce, beforePrompt: current),
        rejected);
    expect(order, baseline);
  });

  test('singleflight spans port instances until native reply', () async {
    final answer = Completer<Object?>();
    final entered = Completer<void>();
    response = () {
      entered.complete();
      return answer.future;
    };
    final pending = port().authorize(nonce, beforePrompt: current);
    await entered.future;
    await expectLater(port().authorize(nonce, beforePrompt: current), rejected);
    expect(calls, hasLength(1));
    answer.complete({'identity_token': 'fictional.payload.signature'});
    expect(await pending, 'fictional.payload.signature');
  });

  test(
      'strict bounded response shape and JWT framing reject without retaining contents',
      () async {
    for (final value in <Object?>[
      null,
      'fictional.payload.signature',
      {},
      {'identity_token': 1},
      {'identity_token': ''},
      {'identity_token': 'not-a-jwt'},
      {'identity_token': 'fictional.payload.signature\n'},
      {'identity_token': 'fictional.payload.signature', 'profile': 'private'},
      {'identity_token': '${'a' * 16384}.b.c'},
    ]) {
      response = () async => value;
      await expectLater(
          port().authorize(nonce, beforePrompt: current), rejected);
    }
  });

  test(
      'native overlap/cancellation/error detail is replaced by fixed safe failure',
      () async {
    for (final code in ['in_progress', 'cancelled', 'unavailable']) {
      response = () async => throw PlatformException(
          code: code,
          message: 'fictional private provider detail',
          details: 'fictional-token');
      try {
        await port().authorize(nonce, beforePrompt: current);
        fail('must reject');
      } on GoogleAuthorizationUnavailable catch (error) {
        expect(error.toString(), isNot(contains('private')));
        expect(error.toString(), isNot(contains('fictional-token')));
      }
    }
    response = () async => {'identity_token': 'fictional.payload.signature'};
    expect(await port().authorize(nonce, beforePrompt: current),
        'fictional.payload.signature');
  });

  test(
      'owner or connectivity change during initialization prevents native prompt',
      () async {
    final initialized = Completer<void>();
    var stillCurrent = true;
    var initializing = false;
    final google = NativeGoogleAuthorization.forTesting('ios', client, server,
        channel: channel, initialize: ({clientId, required serverClientId}) {
      initializing = true;
      return initialized.future;
    });
    final pending = google.authorize(nonce, beforePrompt: () {
      if (!stillCurrent) throw StateError('fictional expired owner');
    });
    final checked = expectLater(pending, rejected);
    expect(initializing, isTrue);
    stillCurrent = false;
    initialized.complete();
    await checked;
    expect(calls, isEmpty);
  });

  test(
      'explicit Google owner opens only after confirmation and uses fresh port',
      () async {
    final store = owner_fixture.OwnerStore();
    final transport = owner_fixture.OwnerTransport();
    final online = ValueNotifier(true);
    addTearDown(online.dispose);
    final session = SessionController(
        transport, store, 'fictional', SecureIds(),
        terminalPurge: () async {});
    final ports = provider_fixture.ProofPorts();
    final owner = AccountErasureOwner(
      store: store,
      session: session,
      transport: transport,
      isOnline: () => online.value,
      connectivity: online,
      google: provider_fixture.GoogleProofPort(ports),
    );
    addTearDown(owner.dispose);
    expect(store.reads, 0);
    expect(ports.nonces, isEmpty);
    await expectLater(
        owner.start(provider: 'google', confirmed: false), throwsException);
    expect(store.reads, 0);
    final flow = await owner.start(provider: 'google', confirmed: true);
    expect(transport.paths, isEmpty);
    await flow.request(confirmed: true);
    expect(flow.jobId, isNotNull);
    expect(transport.provider, 'google');
    expect(ports.nonces, hasLength(1));
    expect(ports.logoutCalls, 0);
    expect(ports.envelopeCalls, 0);
    expect(transport.paths,
        ['/account-erasure/request/challenge', '/account-erasure/request']);
  });
}
