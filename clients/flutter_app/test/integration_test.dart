import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_fictional_client/integration.dart';

class ScriptedTransport implements ApiTransport {
  final List<ApiResponse> responses = [];
  final List<(String, String, Map<String, String>, Map<String, dynamic>?)>
      calls = [];
  Completer<void>? gate;
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    calls.add((method, path, headers, body));
    if (gate != null) await gate!.future;
    return responses.removeAt(0);
  }
}

class FakeLine implements LineLoginPort {
  FakeLine({this.token = 'obvious-fake-id-token', this.error});
  final String token;
  final Object? error;
  int calls = 0;
  @override
  Future<String> login(String nonce) async {
    calls++;
    if (error != null) throw error!;
    return token;
  }

  @override
  Future<void> logout() async {}
}

SessionEnvelope session(String access, String refresh) => SessionEnvelope(
    accessToken: access,
    refreshToken: refresh,
    sessionId: 'session',
    expiresIn: 900);

void main() {
  group('configuration', () {
    test('development is explicit fake only', () {
      expect(AppConfig.parse(flavor: 'development', mode: 'fake').mode,
          ClientMode.fake);
      expect(() => AppConfig.parse(flavor: 'development', mode: ''),
          throwsFormatException);
      expect(
          () => AppConfig.parse(
              flavor: 'development',
              mode: 'real',
              apiBaseUrl: 'https://example.invalid',
              lineChannelId: '1'),
          throwsFormatException);
    });
    test('real configuration requires strict https and channel', () {
      expect(
          AppConfig.parse(
                  flavor: 'staging',
                  mode: 'real',
                  apiBaseUrl: 'https://example.invalid',
                  lineChannelId: '123')
              .mode,
          ClientMode.real);
      for (final url in [
        '',
        'http://example.invalid',
        'https://user@example.invalid',
        'https://example.invalid?q=1'
      ]) {
        expect(
            () => AppConfig.parse(
                flavor: 'production',
                mode: 'real',
                apiBaseUrl: url,
                lineChannelId: '123'),
            throwsFormatException);
      }
      expect(
          () => AppConfig.parse(
              flavor: 'production',
              mode: 'real',
              apiBaseUrl: 'https://example.invalid',
              lineChannelId: ''),
          throwsFormatException);
    });
  });

  group('wire contract', () {
    test('accepts unknown fields but rejects missing and unknown enums', () {
      final person = Person.fromJson({
        'id': 'p',
        'display_name': 'Basic',
        'access_level': 'basic',
        'capabilities': ['games:read'],
        'future': true
      });
      expect(person.id, 'p');
      expect(
          () => Person.fromJson({
                'id': 'p',
                'display_name': 'x',
                'access_level': 'basic',
                'capabilities': ['admin']
              }),
          throwsA(isA<ContractException>()));
      expect(
          () => AttendanceSnapshot.fromJson(
              {'game_id': 'g', 'own_reply': 'maybe'}),
          throwsA(isA<ContractException>()));
      expect(
          () => Game.fromJson(
              {'id': 'g', 'start_at': '2026-01-01T00:00:00+08:00'}),
          throwsA(isA<ContractException>()));
    });
    test('attendance team and mutation notification are typed', () {
      final attendance = AttendanceSnapshot.fromJson({
        'game_id': 'g',
        'own_reply': null,
        'replied': [
          {
            'person_id': 'p',
            'display_name': 'Player',
            'reply': 'arriving_late',
            'qualification': 'team_player'
          }
        ]
      });
      expect(attendance.replied.single.qualification,
          AttendanceQualification.teamPlayer);
      final mutation = MutationResult.fromJson({
        'game_id': 'g',
        'reply': 'attending',
        'changed': true,
        'updated_at': '2026-08-18T12:00:00Z',
        'notification': {'status': 'not_required', 'code': null},
        'idempotent_replay': false,
      });
      expect(mutation.notification.status, NotificationStatus.notRequired);
      expect(
          () => MutationResult.fromJson({
                'game_id': 'g',
                'reply': 'attending',
                'changed': null,
                'updated_at': '2026-08-18T12:00:00Z',
                'idempotent_replay': false,
              }),
          throwsA(isA<ContractException>()));
    });
    test('five canonical replies round trip', () {
      expect(
          AttendanceReply.values
              .map((e) => AttendanceReplyWire.parse(e.wire))
              .toList(),
          AttendanceReply.values);
    });
  });

  test('concurrent callers share one refresh and keep access memory-only',
      () async {
    final api = ScriptedTransport()
      ..responses.add(ApiResponse(200, {
        'access_token': 'new-access',
        'refresh_token': 'new-refresh',
        'session_id': 's',
        'expires_in': 900
      }));
    final store = MemoryStore()..values['refresh:install'] = 'old-refresh';
    final controller = SessionController(api, store, 'install', SecureIds());
    api.gate = Completer<void>();
    final calls = List.generate(10, (_) => controller.refresh());
    await Future<void>.delayed(Duration.zero);
    expect(api.calls, hasLength(1));
    api.gate!.complete();
    expect(await Future.wait(calls), everyElement('new-access'));
    expect(store.values.values, isNot(contains('new-access')));
  });

  test('terminal refresh clears durable session', () async {
    final api = ScriptedTransport()
      ..responses.add(const ApiResponse(401, null));
    final store = MemoryStore()..values['refresh:install'] = 'refresh';
    final controller = SessionController(api, store, 'install', SecureIds());
    await expectLater(controller.refresh(), throwsStateError);
    expect(store.values['refresh:install'], isNull);
  });

  test('401 refreshes once and retries request once', () async {
    final api = ScriptedTransport()
      ..responses.addAll([
        const ApiResponse(401, null),
        ApiResponse(200, {
          'access_token': 'new',
          'refresh_token': 'rotated',
          'session_id': 's',
          'expires_in': 900
        }),
        ApiResponse(200, {
          'id': 'p',
          'display_name': 'Basic',
          'access_level': 'basic',
          'capabilities': ['games:read']
        }),
      ]);
    final store = MemoryStore();
    final controller = SessionController(api, store, 'install', SecureIds());
    await controller.accept(session('old', 'refresh'));
    final result = await controller.authorized('GET', '/me');
    expect(result.status, 200);
    expect(api.calls.map((call) => call.$2), ['/me', '/auth/refresh', '/me']);
    expect(api.calls.last.$3['Authorization'], 'Bearer new');
  });

  test('lost refresh response reuses durable attempt id', () async {
    final api = ScriptedTransport()
      ..responses.addAll([
        const ApiResponse(503, null),
        ApiResponse(200, {
          'access_token': 'new',
          'refresh_token': 'rotated',
          'session_id': 's',
          'expires_in': 900
        }),
      ]);
    final store = MemoryStore()..values['refresh:install'] = 'refresh';
    final controller = SessionController(api, store, 'install', SecureIds());
    await expectLater(controller.refresh(), throwsStateError);
    final attempt = api.calls.first.$3['Refresh-Attempt-ID'];
    expect(await controller.refresh(), 'new');
    expect(api.calls.last.$3['Refresh-Attempt-ID'], attempt);
  });

  test('logout terminal refresh clears pending local state', () async {
    final api = ScriptedTransport()
      ..responses.add(const ApiResponse(401, null));
    final store = MemoryStore()..values['refresh:install'] = 'refresh';
    final controller = SessionController(api, store, 'install', SecureIds());
    await controller.logout(FakeLine());
    expect(store.values['refresh:install'], isNull);
    expect(store.values['logout-pending:install'], isNull);
  });

  test('native login exchange never sends a LINE access token', () async {
    final api = ScriptedTransport()
      ..responses.add(ApiResponse(201, {
        'access_token': 'access',
        'refresh_token': 'refresh-token-with-at-least-32-characters',
        'session_id': 's',
        'expires_in': 900
      }));
    final store = MemoryStore();
    final sessions = SessionController(api, store, 'install', SecureIds());
    final line = FakeLine();
    final login = LoginCoordinator(line, api, sessions, SecureIds(), 'install');
    await login.login('android');
    expect(login.state, LoginState.authenticated);
    expect(api.calls.single.$4!['id_token'], 'obvious-fake-id-token');
    expect(api.calls.single.$4!.keys, isNot(contains('access_token')));
    expect(api.calls.single.$4!['nonce'], hasLength(greaterThanOrEqualTo(16)));
    expect(api.calls.single.$4!['login_attempt_id'],
        hasLength(greaterThanOrEqualTo(16)));
  });

  test('offline mutation is read-only and makes zero transport calls',
      () async {
    final transport = ScriptedTransport();
    final store = MemoryStore();
    final sessions =
        SessionController(transport, store, 'install', SecureIds());
    final api = BasicApi(sessions, store, 'install', SecureIds());
    await expectLater(api.reply('g', AttendanceReply.attending, online: false),
        throwsStateError);
    expect(transport.calls, isEmpty);
    expect(store.values, isEmpty);
  });

  test('uncertain mutation reconciles and removes durable intent', () async {
    final transport = ScriptedTransport()
      ..responses.addAll([
        const ApiResponse(503, null),
        ApiResponse(
            200, {'game_id': 'g', 'own_reply': 'attending', 'replied': []}),
      ]);
    final store = MemoryStore();
    final sessions =
        SessionController(transport, store, 'install', SecureIds());
    await sessions.accept(session('access', 'refresh'));
    final result = await BasicApi(sessions, store, 'install', SecureIds())
        .reply('g', AttendanceReply.attending, online: true);
    expect(result.idempotentReplay, isTrue);
    expect(store.values.keys, isNot(contains('mutation:install:g')));
    expect(transport.calls[0].$3['Idempotency-Key'], isNotEmpty);
  });

  test('cache is versioned, installation partitioned, and typed', () async {
    final store = MemoryStore();
    final cache = BasicCache(store, 'install-a');
    final at = DateTime.utc(2026, 8, 18, 12);
    await cache.save(const Person('p', 'Basic', ['games:read']),
        [Game('g', at, 60, null, null, null)], at);
    final loaded = await cache.load();
    expect(loaded!.person.displayName, 'Basic');
    expect(loaded.games.single.id, 'g');
    expect(loaded.lastSyncedAt, at);
    expect(await BasicCache(MemoryStore(), 'install-b').load(), isNull);
    expect(store.values.keys, everyElement(contains('install-a')));
  });
}
