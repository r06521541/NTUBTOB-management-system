import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:ntubtob_portal/account_erasure_entry.dart';
import 'package:ntubtob_portal/account_erasure_runtime.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/google_authorization.dart';
import 'package:ntubtob_portal/integration.dart';

import 'account_erasure_owner_test.dart' as owner_fixture;
import 'account_erasure_provider_test.dart' as provider_fixture;

class ProbeClient extends http.BaseClient {
  ProbeClient(this.respond);
  final Future<http.StreamedResponse> Function(http.BaseRequest) respond;
  int calls = 0;
  bool closed = false;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    calls++;
    expect(request.method, 'GET');
    expect(request.url.toString(), 'https://example.invalid/health');
    expect(request.headers, isEmpty);
    expect(request.followRedirects, isFalse);
    expect(request.maxRedirects, 0);
    return respond(request);
  }

  @override
  void close() => closed = true;
}

AppConfig config([String flavor = 'staging']) => AppConfig.parse(
    flavor: flavor,
    mode: 'real',
    apiBaseUrl: 'https://example.invalid/api/v1',
    lineChannelId: '1234567890',
    googleClientId: 'fixture-ios.apps.googleusercontent.com',
    googleServerClientId: 'fixture-web.apps.googleusercontent.com');

http.StreamedResponse response([int status = 200, int size = 2]) =>
    http.StreamedResponse(Stream.value(List.filled(size, 32)), status);

void main() {
  for (final provider in ['apple', 'google', 'line']) {
    for (final outcome in ['success', 'failed', 'stale', 'disposed']) {
      test('$provider native pause/resume $outcome has at most one prompt',
          () async {
        final checked = Completer<http.StreamedResponse>();
        final entered = Completer<void>();
        var probes = 0;
        final probe =
            ErasureReachability(config().apiBaseUrl!, clientFactory: () {
          probes++;
          return ProbeClient((_) {
            if (probes == 1) {
              return Future.value(response());
            }
            if (!entered.isCompleted) {
              entered.complete();
            }
            return checked.future;
          });
        });
        await probe.refresh();
        final store = owner_fixture.OwnerStore();
        final transport = owner_fixture.OwnerTransport();
        final ports = provider_fixture.ProofPorts();
        final session = SessionController(
            transport, store, 'fixture', SecureIds(),
            terminalPurge: () async {});
        final options = AccountErasureEntryOptions(
            isOnline: () => probe.online,
            connectivity: probe,
            refreshConnectivity: probe.refresh,
            google: provider_fixture.GoogleProofPort(ports));
        final context = AccountErasureRootContext(
            store: store,
            session: session,
            transport: transport,
            line: ports,
            apple: ports,
            google: options.google,
            options: options,
            requireCurrent: () {});
        final owner = context.createOwner();
        final flow = await owner.start(provider: provider, confirmed: true);
        ports.result = () async {
          probe.lifecycle(AppLifecycleState.inactive);
          probe.lifecycle(AppLifecycleState.paused);
          probe.lifecycle(AppLifecycleState.resumed);
          return 'fictional-proof';
        };
        final pending = flow.request(confirmed: true);
        final failed =
            outcome == 'success' ? null : expectLater(pending, throwsException);
        await entered.future;
        expect(transport.paths, ['/account-erasure/request/challenge']);
        expect(ports.nonces.length, 1);
        if (outcome == 'stale') {
          await session.clear();
        }
        if (outcome == 'disposed') {
          owner.dispose();
        }
        checked.complete(response(outcome == 'failed' ? 503 : 200));
        if (failed != null) {
          await failed;
        } else {
          await pending;
        }
        expect(
            transport.paths
                .where((p) => p == '/account-erasure/request')
                .length,
            outcome == 'success' ? 1 : 0);
        expect(ports.nonces.length, 1);
        expect(ports.logoutCalls, 0);
        owner.dispose();
        probe.dispose();
      });
    }
  }

  testWidgets(
      'real Basic root survives connectivity but not store or platform replacement',
      (tester) async {
    final cfg = config();
    var store = MemoryStore();
    var platform = TargetPlatform.iOS;
    Widget root() => composeAccountErasureRoot(
        config: cfg,
        store: store,
        enabled: 'true',
        platform: platform,
        probeClientFactory: () => ProbeClient((_) async => response()));
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    final first = tester.state(find.byType(BasicBootstrapApp));
    final entry = tester
        .widget<BasicBootstrapApp>(find.byType(BasicBootstrapApp))
        .erasureEntry!;
    await entry.refreshConnectivity!();
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    expect(
        identical(tester.state(find.byType(BasicBootstrapApp)), first), isTrue);
    store = MemoryStore();
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    final second = tester.state(find.byType(BasicBootstrapApp));
    expect(identical(second, first), isFalse);
    expect(entry.isOnline(), isFalse);
    platform = TargetPlatform.android;
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    expect(identical(tester.state(find.byType(BasicBootstrapApp)), second),
        isFalse);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
  test('default and false preserve old root with zero erasure construction',
      () {
    final store = owner_fixture.OwnerStore();
    for (final flag in ['', 'false']) {
      final root = composeAccountErasureRoot(
          config: config(),
          store: store,
          enabled: flag,
          platform: TargetPlatform.iOS,
          probeClientFactory: () => throw StateError('must not construct'),
          enabledBuilder: (_) => throw StateError('must not build'));
      expect(root, isA<BasicBootstrapApp>());
      expect((root as BasicBootstrapApp).erasureEntry, isNull);
    }
    expect(store.reads, 0);
    expect(store.writes, 0);
  });

  test('invalid flag or unsupported target fails closed', () {
    for (final flag in ['TRUE', '1', ' true', 'false ']) {
      expect(() => accountErasureEnabled(flag, config(), TargetPlatform.iOS),
          throwsFormatException);
    }
    expect(
        () => accountErasureEnabled(
            'true', config('production'), TargetPlatform.iOS),
        throwsFormatException);
    expect(
        () => accountErasureEnabled(
            'true',
            AppConfig.parse(flavor: 'development', mode: 'fake'),
            TargetPlatform.iOS),
        throwsFormatException);
    expect(
        () => accountErasureEnabled('true', config(), TargetPlatform.windows),
        throwsFormatException);
    expect(accountErasureEnabled('true', config(), TargetPlatform.android),
        isTrue);
  });

  test('initial unknown is false; bounded public health enables reachability',
      () async {
    final client = ProbeClient((_) async => response());
    final probe =
        ErasureReachability(config().apiBaseUrl!, clientFactory: () => client);
    expect(probe.online, isFalse);
    await probe.refresh();
    expect(probe.online, isTrue);
    expect(client.closed, isTrue);
    probe.dispose();
    expect(probe.online, isFalse);
  });

  test('native return before resumed waits without probing while suspended',
      () async {
    var calls = 0;
    final probe = ErasureReachability(config().apiBaseUrl!, clientFactory: () {
      calls++;
      return ProbeClient((_) async => response());
    });
    probe.lifecycle(AppLifecycleState.paused);
    final pending = probe.refresh();
    await Future<void>.delayed(Duration.zero);
    expect(calls, 0);
    expect(probe.online, isFalse);
    probe.lifecycle(AppLifecycleState.resumed);
    await pending;
    expect(probe.online, isTrue);
    expect(calls, 1);
    probe.dispose();
  });

  test('missing resume stays offline and never opens a probe', () async {
    final probe = ErasureReachability(config().apiBaseUrl!,
        timeout: const Duration(milliseconds: 1),
        clientFactory: () => throw StateError('must not construct'));
    probe.lifecycle(AppLifecycleState.paused);
    await probe.refresh();
    expect(probe.online, isFalse);
    probe.dispose();
  });

  test(
      'redirect, failed status, oversized announced and streamed bodies reject',
      () async {
    for (final result in [
      response(302),
      response(503),
      response(200, 1025),
      http.StreamedResponse(const Stream.empty(), 200, contentLength: 1025)
    ]) {
      final client = ProbeClient((_) async => result);
      final probe = ErasureReachability(config().apiBaseUrl!,
          clientFactory: () => client);
      await probe.refresh();
      expect(probe.online, isFalse);
      expect(client.closed, isTrue);
      expect(client.calls, 1);
      probe.dispose();
    }
  });

  test('overall timeout closes client and rejects late completion', () async {
    final pending = Completer<http.StreamedResponse>();
    final client = ProbeClient((_) => pending.future);
    final probe = ErasureReachability(config().apiBaseUrl!,
        clientFactory: () => client, timeout: const Duration(milliseconds: 1));
    await probe.refresh();
    expect(probe.online, isFalse);
    expect(client.closed, isTrue);
    pending.complete(response());
    await Future<void>.delayed(Duration.zero);
    expect(probe.online, isFalse);
    probe.dispose();
  });

  test('singleflight, pause and disposal fence late replies', () async {
    final pending = Completer<http.StreamedResponse>();
    final client = ProbeClient((_) => pending.future);
    final probe =
        ErasureReachability(config().apiBaseUrl!, clientFactory: () => client);
    final first = probe.refresh();
    expect(identical(first, probe.refresh()), isTrue);
    probe.lifecycle(AppLifecycleState.inactive);
    expect(probe.online, isFalse);
    expect(client.closed, isTrue);
    probe.dispose();
    pending.complete(response());
    await first;
    expect(probe.online, isFalse);
    expect(client.calls, 1);
  });

  test('resume after in-flight pause schedules exactly one fresh probe',
      () async {
    final pending = Completer<http.StreamedResponse>();
    final clients = <ProbeClient>[];
    final probe = ErasureReachability(config().apiBaseUrl!, clientFactory: () {
      final client = ProbeClient((_) =>
          clients.length == 1 ? pending.future : Future.value(response()));
      clients.add(client);
      return client;
    });
    final first = probe.refresh();
    probe.lifecycle(AppLifecycleState.paused);
    probe.lifecycle(AppLifecycleState.resumed);
    pending.complete(response());
    await first;
    await Future<void>.delayed(Duration.zero);
    expect(clients.length, 2);
    expect(probe.online, isTrue);
    probe.dispose();
  });

  testWidgets(
      'enabled root retains options across connectivity and creates no owner',
      (tester) async {
    final store = owner_fixture.OwnerStore();
    final cfg = config();
    final clients = <ProbeClient>[];
    AccountErasureEntryOptions? options;
    Widget root() => composeAccountErasureRoot(
        config: cfg,
        store: store,
        enabled: 'true',
        platform: TargetPlatform.iOS,
        probeClientFactory: () {
          final client = ProbeClient((_) async => response());
          clients.add(client);
          return client;
        },
        enabledBuilder: (value) {
          options = value;
          return const SizedBox();
        });
    await tester.pumpWidget(root());
    await tester.pumpAndSettle();
    final first = options!;
    expect(first.google, isA<NativeGoogleAuthorization>());
    expect(first.ownerFactory, isNull);
    await first.refreshConnectivity!();
    await tester.pumpWidget(root());
    expect(identical(options, first), isTrue);
    expect(store.reads, 0);
    expect(store.writes, 0);
    await tester.pumpWidget(const SizedBox());
    expect(first.isOnline(), isFalse);
    expect(clients.every((client) => client.closed), isTrue);
  });

  testWidgets(
      'manual entry refresh is read-only; offline request never calls provider',
      (tester) async {
    final store = owner_fixture.OwnerStore();
    final transport = owner_fixture.OwnerTransport();
    final ports = provider_fixture.ProofPorts();
    final client = ProbeClient((_) async => response(503));
    final probe =
        ErasureReachability(config().apiBaseUrl!, clientFactory: () => client);
    final context = AccountErasureRootContext(
      store: store,
      session: SessionController(transport, store, 'fixture', SecureIds(),
          terminalPurge: () async {}),
      transport: transport,
      line: ports,
      apple: ports,
      options: AccountErasureEntryOptions(
          isOnline: () => probe.online,
          connectivity: probe,
          refreshConnectivity: probe.refresh),
      requireCurrent: () {},
    );
    final owner = context.createOwner();
    addTearDown(owner.dispose);
    addTearDown(probe.dispose);
    await tester.pumpWidget(MaterialApp(
        home: AccountErasureEntryPage(
            rootContext: context,
            open: ({String? provider, required bool resume}) async =>
                throw StateError('must not open'))));
    await tester
        .tap(find.byKey(const ValueKey('erasure-entry-refresh-connectivity')));
    await tester.pumpAndSettle();
    expect(client.calls, 1);
    expect(probe.online, isFalse);
    expect(store.writes, 0);
    final flow = await owner.start(provider: 'line', confirmed: true);
    await expectLater(flow.request(confirmed: true), throwsException);
    expect(transport.paths, isEmpty);
    expect(ports.nonces, isEmpty);
  });
}
