import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/integration.dart';

class _Call {
  _Call(this.method, this.path, this.headers, this.body);
  final String method;
  final String path;
  final Map<String, String> headers;
  final Map<String, dynamic>? body;
  final reply = Completer<ApiResponse>();
}

class _Transport implements ApiTransport {
  final calls = <_Call>[];

  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) {
    final call = _Call(method, path, headers, body);
    calls.add(call);
    return call.reply.future;
  }
}

class _DelayedStore extends MemoryStore {
  Completer<void>? writeGate;
  Completer<void>? writeStarted;
  Completer<void>? deleteGate;
  Completer<void>? deleteStarted;

  @override
  Future<void> write(String key, String value) async {
    if (key.startsWith('refresh:') && writeGate != null) {
      final gate = writeGate!;
      writeGate = null;
      writeStarted?.complete();
      await gate.future;
    }
    await super.write(key, value);
  }

  @override
  Future<void> delete(String key) async {
    if (key.startsWith('refresh:') && deleteGate != null) {
      final gate = deleteGate!;
      deleteGate = null;
      deleteStarted?.complete();
      await gate.future;
    }
    await super.delete(key);
  }
}

class _Line implements LineLoginPort {
  Completer<void>? gate;
  int logouts = 0;

  @override
  Future<String> login(String nonce) => throw StateError('not used');

  @override
  Future<void> logout() async {
    logouts++;
    await gate?.future;
  }
}

SessionEnvelope _session(String name) => SessionEnvelope(
      accessToken: 'fictional-access-$name',
      refreshToken: 'fictional-refresh-$name-with-at-least-32-characters',
      sessionId: 'fictional-session-$name',
      expiresIn: 900,
    );

ApiResponse _refreshed(String name) => ApiResponse(200, {
      'access_token': _session(name).accessToken,
      'refresh_token': _session(name).refreshToken,
      'session_id': _session(name).sessionId,
      'expires_in': _session(name).expiresIn,
    });

const _personalPrefixes = [
  'cache:v1:fixture:',
  'notification-cache:v1:fixture:',
  'officer-report-cache:v1:fixture:',
  'mutation:fixture:',
  'event-mutation:fixture:',
  'profile-mutation:fixture:',
];

void _seedPersonalData(MemoryStore store, String account) {
  for (final prefix in _personalPrefixes) {
    store.values['$prefix$account'] = 'fictional-$account';
  }
}

Future<void> _purgePersonalData(MemoryStore store) async {
  for (final prefix in _personalPrefixes) {
    await store.deleteKeysWithPrefix(prefix);
  }
}

void _expectPersonalData(MemoryStore store, String account, bool present) {
  for (final prefix in _personalPrefixes) {
    expect(store.values.containsKey('$prefix$account'), present,
        reason: '$prefix$account');
  }
}

void main() {
  test(
      'generation observer refresh queues behind new login credential publication',
      () async {
    final transport = _Transport();
    final session =
        SessionController(transport, MemoryStore(), 'fixture', SecureIds());
    await session.accept(_session('a'));
    Future<String>? observedRefresh;
    session.generationChanges.addListener(() {
      observedRefresh = session.refresh();
    });
    await session.accept(_session('b'));
    await pumpEventQueue();
    final submittedRefresh = transport.calls.single.body!['refresh_token'];
    transport.calls.single.reply.complete(_refreshed('b-renewed'));
    await observedRefresh;
    expect(submittedRefresh, _session('b').refreshToken);
    expect(session.accessToken, _session('b-renewed').accessToken);
  });

  test('generation observer during clear cannot consume cleanup twice',
      () async {
    var purges = 0;
    final transport = _Transport();
    final session = SessionController(
        transport, MemoryStore(), 'fixture', SecureIds(),
        terminalPurge: () async => purges++);
    await session.accept(_session('a'));
    Future<String>? observedRefresh;
    session.generationChanges.addListener(() {
      observedRefresh = session.refresh();
    });
    final clearing = session.clear();
    final rejected = expectLater(observedRefresh, throwsStateError);
    await clearing;
    await rejected;
    expect(transport.calls, isEmpty);
    expect(purges, 1);
  });

  test('generation changes notify synchronously after access is invalidated',
      () async {
    final session =
        SessionController(_Transport(), MemoryStore(), 'fixture', SecureIds());
    expect(session.generationChanges.value, 0);
    final observed = <(int, String?)>[];
    session.generationChanges.addListener(() {
      observed.add((session.generationChanges.value, session.accessToken));
    });
    final accepting = session.accept(_session('a'));
    expect(observed, [(1, null)]);
    await accepting;
    final clearing = session.clear();
    expect(observed, [(1, null), (2, null)]);
    await clearing;
  });

  test('late refresh cannot restore a cleared session', () async {
    final transport = _Transport();
    final store = MemoryStore();
    final session = SessionController(transport, store, 'fixture', SecureIds());
    await session.accept(_session('a'));
    final future = session.refresh();
    final rejected =
        expectLater(future, throwsA(isA<SessionSupersededException>()));
    await pumpEventQueue();
    expect(transport.calls, hasLength(1));
    await session.clear();
    transport.calls.single.reply.complete(_refreshed('a-late'));
    await rejected;
    expect(session.accessToken, isNull);
    expect(store.values, isEmpty);
  });

  for (final status in [200, 401]) {
    test('late refresh $status cannot replace or clear a newer account',
        () async {
      final transport = _Transport();
      final store = MemoryStore();
      var purges = 0;
      final session = SessionController(
        transport,
        store,
        'fixture',
        SecureIds(),
        terminalPurge: () async => purges++,
      );
      await session.accept(_session('a'));
      final future = session.refresh();
      final rejected =
          expectLater(future, throwsA(isA<SessionSupersededException>()));
      await pumpEventQueue();
      await session.accept(_session('b'));
      transport.calls.single.reply.complete(
        status == 200 ? _refreshed('a-late') : const ApiResponse(401, null),
      );
      await rejected;
      expect(session.accessToken, _session('b').accessToken);
      expect(store.values['refresh:fixture'], _session('b').refreshToken);
      expect(purges, 1);
    });
  }

  test('old authorized failure never retries a write as the newer account',
      () async {
    final transport = _Transport();
    final store = MemoryStore();
    final session = SessionController(transport, store, 'fixture', SecureIds());
    await session.accept(_session('a'));
    final future = session.authorized('POST', '/me/account-deletion');
    var completed = false;
    Object? observedError;
    future.then<void>((_) => completed = true, onError: (Object error) {
      completed = true;
      observedError = error;
    });
    await pumpEventQueue();
    await session.accept(_session('b'));
    transport.calls.single.reply.complete(const ApiResponse(401, null));
    await pumpEventQueue();
    // Complete any incorrectly issued second call so a failure leaves no waiter.
    if (transport.calls.length > 1) {
      transport.calls[1].reply.complete(const ApiResponse(200, {}));
      await pumpEventQueue();
    }
    expect(transport.calls, hasLength(1));
    expect(completed, isTrue);
    expect(observedError, isA<SessionSupersededException>());
    expect(session.accessToken, _session('b').accessToken);
  });

  test('old successful response is not exposed to a newer account', () async {
    final transport = _Transport();
    final store = MemoryStore();
    final session = SessionController(transport, store, 'fixture', SecureIds());
    await session.accept(_session('a'));
    final future = session.authorized('GET', '/me');
    final rejected =
        expectLater(future, throwsA(isA<SessionSupersededException>()));
    await pumpEventQueue();
    await session.accept(_session('b'));
    transport.calls.single.reply
        .complete(const ApiResponse(200, {'old': true}));
    await rejected;
    expect(session.accessToken, _session('b').accessToken);
  });

  for (final clearInstead in [true, false]) {
    test(
        'delayed credential write cannot defeat ${clearInstead ? 'clear' : 'new login'}',
        () async {
      final gate = Completer<void>();
      final started = Completer<void>();
      final store = _DelayedStore()
        ..writeGate = gate
        ..writeStarted = started;
      final session =
          SessionController(_Transport(), store, 'fixture', SecureIds());
      final accepting = session.accept(_session('a'));
      final rejected =
          expectLater(accepting, throwsA(isA<SessionSupersededException>()));
      await started.future;
      final generation = session.generation;
      final replacing =
          clearInstead ? session.clear() : session.accept(_session('b'));
      expect(session.generation, generation + 1);
      expect(session.accessToken, isNull);
      gate.complete();
      await rejected;
      await replacing;
      expect(
          session.accessToken, clearInstead ? null : _session('b').accessToken);
      expect(store.values['refresh:fixture'],
          clearInstead ? null : _session('b').refreshToken);
    });
  }

  test('late old refresh cannot clear the new generation single flight',
      () async {
    final transport = _Transport();
    final store = MemoryStore();
    final session = SessionController(transport, store, 'fixture', SecureIds());
    await session.accept(_session('a'));
    final oldRefresh = session.refresh();
    final rejected =
        expectLater(oldRefresh, throwsA(isA<SessionSupersededException>()));
    await pumpEventQueue();
    await session.accept(_session('b'));
    final newRefresh = session.refresh();
    await pumpEventQueue();
    expect(transport.calls, hasLength(2));
    transport.calls.first.reply.complete(_refreshed('a-late'));
    await rejected;
    final sameNewRefresh = session.refresh();
    expect(identical(newRefresh, sameNewRefresh), isTrue);
    expect(transport.calls, hasLength(2));
    transport.calls.last.reply.complete(_refreshed('b-renewed'));
    expect(await newRefresh, _session('b-renewed').accessToken);
    expect(await sameNewRefresh, _session('b-renewed').accessToken);
  });

  for (final status in [204, 401]) {
    test('late logout $status never clears or purges the newer account',
        () async {
      final transport = _Transport();
      final store = MemoryStore();
      final session =
          SessionController(transport, store, 'fixture', SecureIds());
      final line = _Line();
      var purges = 0;
      await session.accept(_session('a'));
      final logout = session.logout(line, purgeLocal: () async => purges++);
      final rejected =
          expectLater(logout, throwsA(isA<SessionSupersededException>()));
      await pumpEventQueue();
      expect(transport.calls.single.path, '/auth/logout');
      await session.accept(_session('b'));
      transport.calls.single.reply.complete(ApiResponse(status, null));
      await rejected;
      expect(line.logouts, 0);
      expect(purges, 1);
      expect(session.accessToken, _session('b').accessToken);
      expect(store.values['refresh:fixture'], _session('b').refreshToken);
      expect(store.values['logout-pending:fixture'], isNull);
    });
  }

  test('late provider logout cannot purge newer account local data', () async {
    final transport = _Transport();
    final store = MemoryStore();
    final session = SessionController(transport, store, 'fixture', SecureIds());
    final line = _Line()..gate = Completer<void>();
    var purges = 0;
    await session.accept(_session('a'));
    _seedPersonalData(store, 'a');
    final logout = session.logout(line, purgeLocal: () async {
      purges++;
      await _purgePersonalData(store);
    });
    final rejected =
        expectLater(logout, throwsA(isA<SessionSupersededException>()));
    await pumpEventQueue();
    transport.calls.single.reply.complete(const ApiResponse(204, null));
    await pumpEventQueue();
    expect(line.logouts, 1);
    await session.accept(_session('b'));
    final oldDataSurvived = store.values.containsKey('cache:v1:fixture:a');
    _seedPersonalData(store, 'b');
    line.gate!.complete();
    await rejected;
    expect(oldDataSurvived, isFalse);
    expect(purges, 1);
    _expectPersonalData(store, 'b', true);
    expect(session.accessToken, _session('b').accessToken);
    expect(store.values['logout-pending:fixture'], isNull);
  });

  test('same-turn clear remains a complete cleanup barrier before new login',
      () async {
    final store = MemoryStore();
    var purges = 0;
    final session = SessionController(
        _Transport(), store, 'fixture', SecureIds(), terminalPurge: () async {
      purges++;
      await _purgePersonalData(store);
    });
    await session.accept(_session('a'));
    _seedPersonalData(store, 'a');
    final clear = session.clear();
    final cleared = expectLater(clear, completes);
    final accepted = session.accept(_session('b'));
    await cleared;
    await accepted;
    _expectPersonalData(store, 'a', false);
    _seedPersonalData(store, 'b');
    await pumpEventQueue();
    _expectPersonalData(store, 'b', true);
    expect(purges, 1);
    expect(session.accessToken, _session('b').accessToken);
    expect(store.values['session-cleanup-pending:fixture'], isNull);
  });

  test(
      'paused credential write cannot cancel queued cleanup before B publishes',
      () async {
    final store = _DelayedStore();
    var purges = 0;
    final session = SessionController(
        _Transport(), store, 'fixture', SecureIds(), terminalPurge: () async {
      purges++;
      await _purgePersonalData(store);
    });
    await session.accept(_session('a'));
    _seedPersonalData(store, 'a');
    final gate = Completer<void>();
    final started = Completer<void>();
    store.writeGate = gate;
    store.writeStarted = started;
    final write = session.accept(_session('a-refresh'), newLogin: false);
    final rejected =
        expectLater(write, throwsA(isA<SessionSupersededException>()));
    await started.future;
    final clear = session.clear();
    final cleared = expectLater(clear, completes);
    final accepted = session.accept(_session('b'));
    gate.complete();
    await rejected;
    await cleared;
    await accepted;
    _expectPersonalData(store, 'a', false);
    _seedPersonalData(store, 'b');
    await pumpEventQueue();
    _expectPersonalData(store, 'b', true);
    expect(purges, 1);
    expect(store.values['refresh:fixture'], _session('b').refreshToken);
  });

  test('cleanup failure blocks queued new credentials and retains cleanup debt',
      () async {
    final store = MemoryStore();
    var fail = true;
    final session = SessionController(
        _Transport(), store, 'fixture', SecureIds(), terminalPurge: () async {
      if (fail) throw StateError('fictional cleanup unavailable');
      await _purgePersonalData(store);
    });
    await session.accept(_session('a'));
    _seedPersonalData(store, 'a');
    final clear = session.clear();
    final rejectedClear = expectLater(clear, throwsStateError);
    final accepted = session.accept(_session('b'));
    await expectLater(accepted, throwsStateError);
    await rejectedClear;
    _expectPersonalData(store, 'a', true);
    expect(session.accessToken, isNull);
    expect(store.values['refresh:fixture'], isNull);
    expect(store.values['session-cleanup-pending:fixture'], 'true');
    fail = false;
    await session.clear();
    await session.accept(_session('b'));
    _expectPersonalData(store, 'a', false);
    expect(session.accessToken, _session('b').accessToken);
    expect(store.values['session-cleanup-pending:fixture'], isNull);
  });

  test(
      'clear paused inside credential deletion completes purge before B publishes',
      () async {
    final store = _DelayedStore();
    var purges = 0;
    final session = SessionController(
        _Transport(), store, 'fixture', SecureIds(), terminalPurge: () async {
      purges++;
      await _purgePersonalData(store);
    });
    await session.accept(_session('a'));
    _seedPersonalData(store, 'a');
    final gate = Completer<void>();
    final started = Completer<void>();
    store.deleteGate = gate;
    store.deleteStarted = started;
    final clearing = session.clear();
    await started.future;
    final accepting = session.accept(_session('b'));
    expect(session.accessToken, isNull);
    gate.complete();
    await clearing;
    await accepting;
    _expectPersonalData(store, 'a', false);
    _seedPersonalData(store, 'b');
    await pumpEventQueue();
    _expectPersonalData(store, 'b', true);
    expect(purges, 1);
    expect(store.values['refresh:fixture'], _session('b').refreshToken);
  });

  for (final refresh in [true, false]) {
    test(
        'late ${refresh ? 'refresh' : 'authorized'} network error is superseded',
        () async {
      final transport = _Transport();
      final session =
          SessionController(transport, MemoryStore(), 'fixture', SecureIds());
      await session.accept(_session('a'));
      final Future<Object> request =
          refresh ? session.refresh() : session.authorized('GET', '/me');
      final rejected =
          expectLater(request, throwsA(isA<SessionSupersededException>()));
      await pumpEventQueue();
      await session.accept(_session('b'));
      transport.calls.single.reply.completeError(const NetworkException());
      await rejected;
      expect(session.accessToken, _session('b').accessToken);
    });

    test(
        'current ${refresh ? 'refresh' : 'authorized'} network error keeps classification',
        () async {
      final transport = _Transport();
      final session =
          SessionController(transport, MemoryStore(), 'fixture', SecureIds());
      await session.accept(_session('a'));
      final Future<Object> request =
          refresh ? session.refresh() : session.authorized('GET', '/me');
      final rejected = expectLater(
          request,
          throwsA(refresh
              ? isA<NetworkException>().having(
                  (error) => error.runtimeType, 'exact type', NetworkException)
              : isA<AuthorizedRequestNetworkException>()));
      await pumpEventQueue();
      transport.calls.single.reply.completeError(const NetworkException());
      await rejected;
      expect(session.accessToken, _session('a').accessToken);
    });
  }

  for (final fail in [true, false]) {
    test(
        'restart cleanup marker ${fail ? 'fails closed' : 'clears before refresh'}',
        () async {
      final store = MemoryStore()
        ..values['refresh:fixture'] = _session('a').refreshToken
        ..values['session-cleanup-pending:fixture'] = 'true';
      _seedPersonalData(store, 'a');
      final transport = _Transport();
      final session = SessionController(
          transport, store, 'fixture', SecureIds(), terminalPurge: () async {
        if (fail) throw StateError('fictional cleanup unavailable');
        await _purgePersonalData(store);
      });
      final refresh = session.refresh();
      Object? resultError;
      refresh.then<void>((_) {},
          onError: (Object error) => resultError = error);
      await pumpEventQueue();
      // Release a wrongly dispatched network request before asserting RED.
      if (transport.calls.isNotEmpty) {
        transport.calls.single.reply.complete(const ApiResponse(503, null));
        await pumpEventQueue();
      }
      expect(resultError, isA<StateError>());
      expect(transport.calls, isEmpty);
      _expectPersonalData(store, 'a', fail);
      expect(store.values['session-cleanup-pending:fixture'],
          fail ? 'true' : null);
      expect(session.accessToken, isNull);
    });
  }

  for (final refresh in [true, false]) {
    test(
        'terminal ${refresh ? 'refresh' : 'authorized'} cleanup cannot expire a newer login',
        () async {
      final transport = _Transport();
      final store = MemoryStore();
      final purgeStarted = Completer<void>();
      final purgeGate = Completer<void>();
      final session = SessionController(
          transport, store, 'fixture', SecureIds(), terminalPurge: () async {
        purgeStarted.complete();
        await purgeGate.future;
        await _purgePersonalData(store);
      });
      await session.accept(_session('a'));
      _seedPersonalData(store, 'a');
      final Future<Object> request =
          refresh ? session.refresh() : session.authorized('GET', '/me');
      final rejected =
          expectLater(request, throwsA(isA<SessionSupersededException>()));
      await pumpEventQueue();
      transport.calls.first.reply.complete(const ApiResponse(401, null));
      if (!refresh) {
        await pumpEventQueue();
        transport.calls[1].reply.complete(_refreshed('a-renewed'));
        await pumpEventQueue();
        transport.calls[2].reply.complete(const ApiResponse(401, null));
      }
      await purgeStarted.future;
      final accepting = session.accept(_session('b'));
      purgeGate.complete();
      await rejected;
      await accepting;
      _expectPersonalData(store, 'a', false);
      expect(session.accessToken, _session('b').accessToken);
    });
  }

  test('same account refresh and authorized retry retain request binding',
      () async {
    final transport = _Transport();
    final store = MemoryStore();
    final session = SessionController(transport, store, 'fixture', SecureIds());
    await session.accept(_session('a'));
    final generation = session.generation;
    final result = session.authorized('POST', '/fixture',
        headers: {'Idempotency-Key': 'same-fictional-key'});
    await pumpEventQueue();
    transport.calls[0].reply.complete(const ApiResponse(401, null));
    await pumpEventQueue();
    expect(transport.calls[1].path, '/auth/refresh');
    transport.calls[1].reply.complete(_refreshed('a-renewed'));
    await pumpEventQueue();
    expect(transport.calls[2].headers['Authorization'],
        'Bearer ${_session('a-renewed').accessToken}');
    expect(transport.calls[2].headers['Idempotency-Key'], 'same-fictional-key');
    transport.calls[2].reply.complete(const ApiResponse(202, {}));
    expect((await result).status, 202);
    expect(session.generation, generation);
  });
}
