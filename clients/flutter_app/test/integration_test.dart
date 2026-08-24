import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ntubtob_portal/integration.dart';

class ScriptedTransport implements ApiTransport {
  final List<ApiResponse> responses = [];
  final List<(String, String, Map<String, String>, Map<String, dynamic>?)>
      calls = [];
  Completer<void>? gate;
  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    calls.add((method, path, headers, body));
    if (gate != null) await gate!.future;
    return responses.removeAt(0);
  }
}

class NetworkScriptTransport implements ApiTransport {
  final List<Object> outcomes;
  NetworkScriptTransport(this.outcomes);
  final List<(String, String, Map<String, String>, Map<String, dynamic>?)>
      calls = [];
  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    calls.add((method, path, headers, body));
    final outcome = outcomes.removeAt(0);
    if (outcome is ApiResponse) return outcome;
    throw outcome;
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

class FakeGoogle implements GoogleLoginPort {
  int calls = 0;
  @override
  Future<String> login() async {
    calls++;
    return 'obvious-fake-google-id-token';
  }

  @override
  Future<void> logout() async {}
}

class PendingLine implements LineLoginPort {
  int calls = 0;
  final Completer<String> completer = Completer<String>();
  @override
  Future<String> login(String nonce) {
    calls++;
    return completer.future;
  }

  @override
  Future<void> logout() async {}
}

class ControlledLine implements LineLoginPort {
  int calls = 0;
  final List<Completer<String>> attempts = [];
  @override
  Future<String> login(String nonce) {
    calls++;
    final completer = Completer<String>();
    attempts.add(completer);
    return completer.future;
  }

  @override
  Future<void> logout() async {}
}

class SequenceIds extends SecureIds {
  int index = 0;
  @override
  String next() => [
        'expired-attempt',
        'expired-nonce',
        'fresh-attempt',
        'fresh-nonce',
      ][index++];
}

class FailingWriteStore extends MemoryStore {
  @override
  Future<void> write(String key, String value) async {
    if (key.startsWith('refresh:')) throw StateError('secure write failed');
    await super.write(key, value);
  }
}

class FailingPrefixDeleteStore extends MemoryStore {
  @override
  Future<void> deleteKeysWithPrefix(String prefix) async {
    if (prefix.startsWith('mutation:')) {
      throw StateError('bounded purge failed');
    }
    await super.deleteKeysWithPrefix(prefix);
  }
}

class Concurrent401Transport implements ApiTransport {
  final Completer<void> allInitialRequests = Completer<void>();
  int initialCount = 0;
  int refreshCount = 0;
  int replayCount = 0;
  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    if (path == '/auth/refresh') {
      refreshCount++;
      return ApiResponse(200, {
        'access_token': 'new-access',
        'refresh_token': 'new-refresh-token-with-more-than-32-characters',
        'session_id': 's',
        'expires_in': 900,
      });
    }
    if (headers['Authorization'] == 'Bearer old-access') {
      initialCount++;
      if (initialCount == 10) allInitialRequests.complete();
      await allInitialRequests.future;
      return const ApiResponse(401, null);
    }
    replayCount++;
    return const ApiResponse(200, {});
  }
}

Map<String, dynamic> apiError(String code, {bool retryable = false}) => {
      'error': {
        'code': code,
        'message': 'safe message',
        'request_id': 'request',
        'retryable': retryable,
        'retry_after_seconds': null,
        'field_errors': [],
      },
    };

Map<String, dynamic> gameJson(String id) => {
      'id': id,
      'start_at': '2026-08-18T12:00:00Z',
      'duration_minutes': 60,
      'location': null,
      'home_team': 'Home',
      'away_team': 'Away',
    };

Map<String, dynamic> mutationJson(String reply) => {
      'game_id': 'g',
      'reply': reply,
      'changed': true,
      'updated_at': '2026-08-18T12:00:00Z',
      'notification': {'status': 'not_required', 'code': null},
      'idempotent_replay': false,
    };

SessionEnvelope session(String access, String refresh) => SessionEnvelope(
      accessToken: access,
      refreshToken: refresh,
      sessionId: 'session',
      expiresIn: 900,
    );

void main() {
  group('configuration', () {
    test('development is explicit fake only', () {
      expect(
        AppConfig.parse(flavor: 'development', mode: 'fake').mode,
        ClientMode.fake,
      );
      expect(
        () => AppConfig.parse(flavor: 'development', mode: ''),
        throwsFormatException,
      );
      expect(
        () => AppConfig.parse(
          flavor: 'development',
          mode: 'real',
          apiBaseUrl: 'https://example.invalid',
          lineChannelId: '1',
        ),
        throwsFormatException,
      );
      expect(
        () => AppConfig.parse(
          flavor: 'staging',
          mode: 'real',
          apiBaseUrl: 'https://example.invalid',
          lineChannelId: '123',
          googleClientId: 'not-a-client-id',
          googleServerClientId: 'web-server.apps.googleusercontent.com',
        ),
        throwsFormatException,
      );
    });
    test('real configuration requires strict https and channel', () {
      expect(
        AppConfig.parse(
          flavor: 'staging',
          mode: 'real',
          apiBaseUrl: 'https://example.invalid',
          lineChannelId: '123',
          googleClientId: 'ios-client.apps.googleusercontent.com',
          googleServerClientId: 'server-client.apps.googleusercontent.com',
        ).mode,
        ClientMode.real,
      );
      for (final url in [
        '',
        'http://example.invalid',
        'https://user@example.invalid',
        'https://example.invalid?q=1',
      ]) {
        expect(
          () => AppConfig.parse(
            flavor: 'production',
            mode: 'real',
            apiBaseUrl: url,
            lineChannelId: '123',
          ),
          throwsFormatException,
        );
      }
      expect(
        () => AppConfig.parse(
          flavor: 'production',
          mode: 'real',
          apiBaseUrl: 'https://example.invalid',
          lineChannelId: '',
        ),
        throwsFormatException,
      );
    });
  });

  group('process-wide Google SDK configuration', () {
    setUp(GoogleSignInProcessInitializer.resetForTest);
    tearDown(GoogleSignInProcessInitializer.resetForTest);

    test('compatible concurrent Android initialization occurs exactly once',
        () async {
      var calls = 0;
      Future<void> initialize(
          {String? clientId, required String serverClientId}) async {
        calls += 1;
        expect(clientId, isNull);
        expect(serverClientId, 'web-server.apps.googleusercontent.com');
      }

      await Future.wait([
        GoogleSignInProcessInitializer.ensure(
          platform: 'android',
          clientId: 'unused-ios.apps.googleusercontent.com',
          serverClientId: 'web-server.apps.googleusercontent.com',
          initialize: initialize,
        ),
        GoogleSignInProcessInitializer.ensure(
          platform: 'android',
          clientId: 'another-unused.apps.googleusercontent.com',
          serverClientId: 'web-server.apps.googleusercontent.com',
          initialize: initialize,
        ),
      ]);
      expect(calls, 1);
    });

    test('iOS requires its client ID and conflicting re-init fails closed',
        () async {
      var calls = 0;
      await GoogleSignInProcessInitializer.ensure(
        platform: 'ios',
        clientId: 'ios-client.apps.googleusercontent.com',
        serverClientId: 'web-server.apps.googleusercontent.com',
        initialize: ({clientId, required serverClientId}) async {
          calls += 1;
          expect(clientId, 'ios-client.apps.googleusercontent.com');
        },
      );
      expect(
        () => GoogleSignInProcessInitializer.ensure(
          platform: 'ios',
          clientId: 'different-ios.apps.googleusercontent.com',
          serverClientId: 'web-server.apps.googleusercontent.com',
          initialize: ({clientId, required serverClientId}) async {},
        ),
        throwsStateError,
      );
      expect(calls, 1);
    });

    test('unsupported and incomplete platform configuration fails closed', () {
      Future<void> initialize(
          {String? clientId, required String serverClientId}) async {}
      for (final values in [
        (
          'windows',
          'ios-client.apps.googleusercontent.com',
          'web-server.apps.googleusercontent.com'
        ),
        ('ios', '', 'web-server.apps.googleusercontent.com'),
        (
          'ios',
          'same-client.apps.googleusercontent.com',
          'same-client.apps.googleusercontent.com'
        ),
        ('android', '', ''),
      ]) {
        GoogleSignInProcessInitializer.resetForTest();
        expect(
          () => GoogleSignInProcessInitializer.ensure(
            platform: values.$1,
            clientId: values.$2,
            serverClientId: values.$3,
            initialize: initialize,
          ),
          throwsFormatException,
        );
      }
    });
  });

  test('iOS Google scheme is private, injected, and build-phase validated', () {
    final plist = File('ios/Runner/Info.plist').readAsStringSync();
    final project =
        File('ios/Runner.xcodeproj/project.pbxproj').readAsStringSync();
    final validator = File('ios/validate_auth_config.sh').readAsStringSync();
    final template =
        File('ios/Flutter/AuthConfig.xcconfig.example').readAsStringSync();
    final ignores = File('.gitignore').readAsStringSync();
    expect(plist, contains(r'<string>$(GOOGLE_REVERSED_CLIENT_ID)</string>'));
    expect(plist, contains(r'line3rdp.$(PRODUCT_BUNDLE_IDENTIFIER)'));
    expect(project, contains('Validate Auth Config'));
    expect(project, contains(r'$SRCROOT/validate_auth_config.sh'));
    expect(validator, contains('DART_DEFINES'));
    expect(validator, contains('expected_reversed_client_id'));
    expect(validator, contains('development fake iOS build'));
    expect(template.trimRight(), endsWith('GOOGLE_REVERSED_CLIENT_ID='));
    expect(ignores, contains('ios/Flutter/AuthConfig.xcconfig'));
    expect(plist, isNot(contains('.apps.googleusercontent.com')));
  });

  test('iOS auth validator binds real IDs and permits clean fake builds',
      () async {
    if (Platform.isWindows) return;
    final root = await Directory.systemTemp.createTemp('ios-auth-contract-');
    addTearDown(() => root.delete(recursive: true));
    final runner = Directory('${root.path}/Runner')..createSync();
    File('${runner.path}/Info.plist').writeAsStringSync(
      r'<string>$(GOOGLE_REVERSED_CLIENT_ID)</string>',
    );

    String encodedDefines(Map<String, String> values) => values.entries
        .map(
            (entry) => base64Encode(utf8.encode('${entry.key}=${entry.value}')))
        .join(',');

    Future<ProcessResult> validate(
      Map<String, String> values, {
      String reversed = '',
    }) =>
        Process.run(
          '/bin/sh',
          ['ios/validate_auth_config.sh'],
          environment: {
            'SRCROOT': root.path,
            'DART_DEFINES': encodedDefines(values),
            'GOOGLE_REVERSED_CLIENT_ID': reversed,
          },
        );

    expect(
      (await validate({'APP_FLAVOR': 'development', 'CLIENT_MODE': 'fake'}))
          .exitCode,
      0,
    );
    const iosClient = '123-ios.apps.googleusercontent.com';
    const serverClient = '456-web.apps.googleusercontent.com';
    final real = {
      'APP_FLAVOR': 'staging',
      'CLIENT_MODE': 'real',
      'GOOGLE_CLIENT_ID': iosClient,
      'GOOGLE_SERVER_CLIENT_ID': serverClient,
    };
    final validReal =
        await validate(real, reversed: 'com.googleusercontent.apps.123-ios');
    expect(validReal.exitCode, 0,
        reason: '${validReal.stdout}\n${validReal.stderr}');
    expect(
      (await validate(real, reversed: 'com.googleusercontent.apps.999-other'))
          .exitCode,
      2,
    );
    expect(
      (await validate({
        ...real,
        'GOOGLE_SERVER_CLIENT_ID': iosClient,
      }, reversed: 'com.googleusercontent.apps.123-ios'))
          .exitCode,
      2,
    );
    expect(
      (await validate({
        'APP_FLAVOR': 'development',
        'CLIENT_MODE': 'fake',
        'GOOGLE_CLIENT_ID': iosClient,
      }, reversed: 'com.googleusercontent.apps.123-ios'))
          .exitCode,
      2,
    );
  });

  group('wire contract', () {
    test('accepts unknown fields but rejects missing and unknown enums', () {
      final person = Person.fromJson({
        'id': 'p',
        'display_name': 'Basic',
        'access_level': 'basic',
        'capabilities': ['games:read'],
        'future': true,
      });
      expect(person.id, 'p');
      final officer = Person.fromJson({
        'id': 'officer',
        'display_name': 'Officer',
        'access_level': 'officer',
        'capabilities': [
          'games:read',
          'attendance:reply:self',
          'attendance:report:read',
        ],
      });
      expect(officer.accessLevel, AccessLevel.officer);
      expect(officer.canReadAttendanceReport, isTrue);
      expect(
        () => Person.fromJson({
          'id': 'p',
          'display_name': 'x',
          'access_level': 'basic',
          'capabilities': ['admin'],
        }),
        throwsA(isA<ContractException>()),
      );
      expect(
        () =>
            AttendanceSnapshot.fromJson({'game_id': 'g', 'own_reply': 'maybe'}),
        throwsA(isA<ContractException>()),
      );
      expect(
        () =>
            Game.fromJson({'id': 'g', 'start_at': '2026-01-01T00:00:00+08:00'}),
        throwsA(isA<ContractException>()),
      );
    });
    test('canonical attendance report DTO enforces exact bounded values', () {
      final report = AttendanceReport.fromJson({
        'game_id': 'game_44',
        'generated_at': '2026-08-18T12:00:00Z',
        'observation': {
          'history_games': 8,
          'history_limit': 12,
          'minimum_response_rate': 60,
        },
        'attending': [
          {'person_id': 'person_1', 'display_name': 'A', 'reply': 'attending'},
        ],
        'not_attending': [],
        'not_yet_replied': [
          {
            'person_id': 'person_2',
            'display_name': 'B',
            'observed_replies': 7,
            'observed_games': 8,
            'response_rate': 88,
            'participation_rate': 63,
            'nonparticipation_rate': 25,
          },
        ],
      });
      expect(report.attending.single.reply, AttendanceReply.attending);
      expect(report.notYetReplied.single.responseRate, 88);
      for (final invalidNumber in [-1, 1000]) {
        expect(
          () => AttendanceReportPerson.fromJson({
            'person_id': 'person_1',
            'display_name': 'A',
            'reply': 'attending',
            'member_number': invalidNumber,
          }),
          throwsA(isA<ContractException>()),
        );
      }
      expect(
        () => AttendanceReportObservation.fromJson({
          'history_games': 8,
          'history_limit': 9,
          'minimum_response_rate': 60,
        }),
        throwsA(isA<ContractException>()),
      );
      expect(
        () => AttendanceReportObservation.fromJson({
          'history_games': 8,
          'history_limit': 12,
          'minimum_response_rate': 65,
        }),
        throwsA(isA<ContractException>()),
      );
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
            'qualification': 'team_player',
          },
        ],
      });
      expect(
        attendance.replied.single.qualification,
        AttendanceQualification.teamPlayer,
      );
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
        throwsA(isA<ContractException>()),
      );
    });
    test('five canonical replies round trip', () {
      expect(
        AttendanceReply.values
            .map((e) => AttendanceReplyWire.parse(e.wire))
            .toList(),
        AttendanceReply.values,
      );
    });
  });

  test(
    'concurrent callers share one refresh and keep access memory-only',
    () async {
      final api = ScriptedTransport()
        ..responses.add(
          ApiResponse(200, {
            'access_token': 'new-access',
            'refresh_token': 'new-refresh',
            'session_id': 's',
            'expires_in': 900,
          }),
        );
      final store = MemoryStore()..values['refresh:install'] = 'old-refresh';
      final controller = SessionController(api, store, 'install', SecureIds());
      api.gate = Completer<void>();
      final calls = List.generate(10, (_) => controller.refresh());
      await Future<void>.delayed(Duration.zero);
      expect(api.calls, hasLength(1));
      api.gate!.complete();
      expect(await Future.wait(calls), everyElement('new-access'));
      expect(store.values.values, isNot(contains('new-access')));
    },
  );

  test('terminal refresh clears durable session', () async {
    final api = ScriptedTransport()
      ..responses.add(const ApiResponse(401, null));
    final store = MemoryStore()..values['refresh:install'] = 'refresh';
    final controller = SessionController(api, store, 'install', SecureIds());
    await expectLater(
      controller.refresh(),
      throwsA(isA<SessionExpiredException>()),
    );
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
          'expires_in': 900,
        }),
        ApiResponse(200, {
          'id': 'p',
          'display_name': 'Basic',
          'access_level': 'basic',
          'capabilities': ['games:read'],
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

  test(
    'second 401 clears access and refresh without a third request',
    () async {
      final api = ScriptedTransport()
        ..responses.addAll([
          const ApiResponse(401, null),
          ApiResponse(200, {
            'access_token': 'new',
            'refresh_token': 'rotated',
            'session_id': 's',
            'expires_in': 900,
          }),
          ApiResponse(401, apiError('session_expired')),
        ]);
      final store = MemoryStore();
      final controller = SessionController(api, store, 'install', SecureIds());
      await controller.accept(session('old', 'refresh'));
      await expectLater(
        controller.authorized('GET', '/me'),
        throwsA(isA<SessionExpiredException>()),
      );
      expect(api.calls.map((call) => call.$2), ['/me', '/auth/refresh', '/me']);
      expect(controller.accessToken, isNull);
      expect(store.values['refresh:install'], isNull);
    },
  );

  test(
    '10 concurrent 401s share one refresh and replay each request once',
    () async {
      final transport = Concurrent401Transport();
      final store = MemoryStore();
      final controller = SessionController(
        transport,
        store,
        'install',
        SecureIds(),
      );
      await controller.accept(
        session('old-access', 'old-refresh-token-with-more-than-32-characters'),
      );
      final responses = await Future.wait(
        List.generate(10, (index) => controller.authorized('GET', '/me')),
      );
      expect(responses, everyElement(isA<ApiResponse>()));
      expect(transport.initialCount, 10);
      expect(transport.refreshCount, 1);
      expect(transport.replayCount, 10);
    },
  );

  test(
    'secure-store write failure accepts no memory or durable session',
    () async {
      final store = FailingWriteStore();
      final controller = SessionController(
        ScriptedTransport(),
        store,
        'install',
        SecureIds(),
      );
      await expectLater(
        controller.accept(session('access', 'refresh')),
        throwsStateError,
      );
      expect(controller.accessToken, isNull);
      expect(store.values['refresh:install'], isNull);
    },
  );

  test('lost refresh response reuses durable attempt id', () async {
    final api = ScriptedTransport()
      ..responses.addAll([
        const ApiResponse(503, null),
        ApiResponse(200, {
          'access_token': 'new',
          'refresh_token': 'rotated',
          'session_id': 's',
          'expires_in': 900,
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

  test('logout_pending restart retries and clears durable marker', () async {
    final api = ScriptedTransport()
      ..responses.add(const ApiResponse(204, null));
    final store = MemoryStore()
      ..values['refresh:install'] = 'refresh'
      ..values['logout-pending:install'] = 'true';
    final restarted = SessionController(api, store, 'install', SecureIds());
    await restarted.accept(session('access', 'refresh'));
    await restarted.logout(FakeLine());
    expect(store.values['logout-pending:install'], isNull);
    expect(restarted.accessToken, isNull);
  });

  test(
    'terminal logout retries only local purge after server success',
    () async {
      final api = ScriptedTransport()
        ..responses.add(const ApiResponse(204, null));
      final store = FailingPrefixDeleteStore();
      final controller = SessionController(api, store, 'install', SecureIds());
      await controller.accept(session('access', 'refresh'));

      await expectLater(
        controller.logout(
          FakeLine(),
          purgeLocal: () => store.deleteKeysWithPrefix('mutation:install:'),
        ),
        throwsStateError,
      );
      expect(store.values['logout-pending:install'], 'true');
      expect(store.values['refresh:install'], isNull);
      expect(
        api.calls.where((call) => call.$2 == '/auth/logout'),
        hasLength(1),
      );

      await controller.logout(FakeLine(), purgeLocal: () async {});
      expect(store.values['logout-pending:install'], isNull);
      expect(
        api.calls.where((call) => call.$2 == '/auth/logout'),
        hasLength(1),
      );
    },
  );

  test('native login exchange never sends a LINE access token', () async {
    final api = ScriptedTransport()
      ..responses.add(
        ApiResponse(201, {
          'access_token': 'access',
          'refresh_token': 'refresh-token-with-at-least-32-characters',
          'session_id': 's',
          'expires_in': 900,
        }),
      );
    final store = MemoryStore();
    final sessions = SessionController(api, store, 'install', SecureIds());
    final line = FakeLine();
    final login = LoginCoordinator(line, api, sessions, SecureIds(), 'install');
    await login.login('android');
    expect(login.state, LoginState.authenticated);
    expect(api.calls.single.$4!['id_token'], 'obvious-fake-id-token');
    expect(api.calls.single.$4!.keys, isNot(contains('access_token')));
    expect(api.calls.single.$4!['nonce'], hasLength(greaterThanOrEqualTo(16)));
    expect(
      api.calls.single.$4!['login_attempt_id'],
      hasLength(greaterThanOrEqualTo(16)),
    );
  });

  test('pending review belongs only to its 202 login attempt', () async {
    final api = ScriptedTransport()
      ..responses.addAll([
        const ApiResponse(202, {
          'review_credential': 'review-A',
          'expires_in': 600,
          'status': 'pending',
        }),
        ApiResponse(201, {
          'access_token': 'access-B',
          'refresh_token': 'refresh-token-with-at-least-32-characters',
          'session_id': 'session-B',
          'expires_in': 900,
        }),
        ApiResponse(409, apiError('identity_pending')),
      ]);
    final sessions =
        SessionController(api, MemoryStore(), 'install', SecureIds());
    final login =
        LoginCoordinator(FakeLine(), api, sessions, SecureIds(), 'install');

    await login.login('android');
    expect(login.pendingReview?.credential, 'review-A');
    await login.login('android');
    expect(login.state, LoginState.authenticated);
    expect(login.pendingReview, isNull);
    await login.login('android');
    expect(login.state, LoginState.identityPending);
    expect(login.pendingReview, isNull);
  });

  test('Google 202 remains a review credential and never a normal session',
      () async {
    final api = ScriptedTransport()
      ..responses.add(const ApiResponse(202, {
        'review_credential': 'google-review-only',
        'expires_in': 600,
        'status': 'pending',
      }));
    final store = MemoryStore();
    final google = FakeGoogle();
    final login = GoogleLoginCoordinator(
      google,
      api,
      SessionController(api, store, 'install', SecureIds()),
      SecureIds(),
      'install',
    );
    await login.login('android');
    expect(login.state, LoginState.identityPending);
    expect(login.pendingReview?.credential, 'google-review-only');
    expect(await store.read('refresh:install'), isNull);
    expect(api.calls.single.$2, '/auth/google/exchange');
  });

  test('profile retry key is scoped to person and session generation',
      () async {
    final transport = NetworkScriptTransport([
      const NetworkException(),
      ApiResponse(200, {
        'person': {
          'id': 'person-B',
          'display_name': 'B',
          'access_level': 'basic',
          'capabilities': ['games:read'],
        },
        'changed': true,
        'idempotent_replay': false,
      }),
    ]);
    final store = MemoryStore();
    final sessions =
        SessionController(transport, store, 'install', SecureIds());
    await sessions.accept(const SessionEnvelope(
      accessToken: 'access-A',
      refreshToken: 'refresh-token-with-at-least-32-characters',
      sessionId: 'session-A',
      expiresIn: 900,
    ));
    final api = BasicApi(sessions, store, 'install', SecureIds());
    await expectLater(
      api.updateDisplayName('A', personId: 'person-A'),
      throwsA(isA<ProfileMutationUncertainException>()),
    );
    final firstKey = transport.calls.single.$3['Idempotency-Key'];
    await sessions.clear();
    await sessions.accept(const SessionEnvelope(
      accessToken: 'access-B',
      refreshToken: 'refresh-token-with-at-least-32-characters',
      sessionId: 'session-B',
      expiresIn: 900,
    ));
    await api.updateDisplayName('B', personId: 'person-B');
    expect(transport.calls.last.$3['Idempotency-Key'], isNot(firstKey));
  });

  test('profile uncertain retry reuses key only for same person and session',
      () async {
    final transport = NetworkScriptTransport([
      const NetworkException(),
      const NetworkException(),
      const NetworkException(),
    ]);
    final sessions =
        SessionController(transport, MemoryStore(), 'install', SecureIds());
    await sessions.accept(const SessionEnvelope(
      accessToken: 'access',
      refreshToken: 'refresh-token-with-at-least-32-characters',
      sessionId: 'session',
      expiresIn: 900,
    ));
    final api = BasicApi(sessions, sessions.store, 'install', SecureIds());
    for (var i = 0; i < 2; i++) {
      await expectLater(api.updateDisplayName('A', personId: 'person-A'),
          throwsA(isA<ProfileMutationUncertainException>()));
    }
    expect(transport.calls[0].$3['Idempotency-Key'],
        transport.calls[1].$3['Idempotency-Key']);
    await expectLater(api.updateDisplayName('B', personId: 'person-B'),
        throwsA(isA<ProfileMutationUncertainException>()));
    expect(transport.calls[2].$3['Idempotency-Key'],
        isNot(transport.calls[1].$3['Idempotency-Key']));
  });

  test('profile key survives 401 refresh rotation and uncertain PATCH retry',
      () async {
    final transport = NetworkScriptTransport([
      const ApiResponse(401, null),
      ApiResponse(200, {
        'access_token': 'rotated-access',
        'refresh_token': 'rotated-refresh-token-with-at-least-32-characters',
        'session_id': 'same-login-session',
        'expires_in': 900,
      }),
      const NetworkException(),
      const NetworkException(),
    ]);
    final store = MemoryStore();
    final sessions =
        SessionController(transport, store, 'install', SecureIds());
    await sessions.accept(const SessionEnvelope(
      accessToken: 'initial-access',
      refreshToken: 'initial-refresh-token-with-at-least-32-characters',
      sessionId: 'same-login-session',
      expiresIn: 900,
    ));
    final generation = sessions.generation;
    final api = BasicApi(sessions, store, 'install', SecureIds());
    await expectLater(api.updateDisplayName('A', personId: 'person-A'),
        throwsA(isA<ProfileMutationUncertainException>()));
    expect(sessions.generation, generation);
    await expectLater(api.updateDisplayName('A', personId: 'person-A'),
        throwsA(isA<ProfileMutationUncertainException>()));
    final patchKeys = transport.calls
        .where((call) => call.$1 == 'PATCH')
        .map((call) => call.$3['Idempotency-Key'])
        .toList();
    expect(patchKeys, hasLength(3));
    expect(patchKeys.toSet(), hasLength(1));
  });

  test('canonical identity states and native cancel are classified', () async {
    for (final entry in {
      'identity_pending': LoginState.identityPending,
      'account_unavailable': LoginState.accountUnavailable,
    }.entries) {
      final api = ScriptedTransport()
        ..responses.add(ApiResponse(409, apiError(entry.key)));
      final login = LoginCoordinator(
        FakeLine(),
        api,
        SessionController(api, MemoryStore(), 'install', SecureIds()),
        SecureIds(),
        'install',
      );
      await login.login('android');
      expect(login.state, entry.value);
    }
    final api = ScriptedTransport();
    final cancelled = LoginCoordinator(
      FakeLine(error: PlatformException(code: 'CANCELLED')),
      api,
      SessionController(api, MemoryStore(), 'install', SecureIds()),
      SecureIds(),
      'install',
    );
    await cancelled.login('android');
    expect(cancelled.state, LoginState.cancelled);
    expect(api.calls, isEmpty);
  });

  test('native timeout remains unresolved and performs no exchange', () async {
    final api = ScriptedTransport();
    final line = PendingLine();
    final login = LoginCoordinator(
      line,
      api,
      SessionController(api, MemoryStore(), 'install', SecureIds()),
      SecureIds(),
      'install',
      loginTimeout: const Duration(milliseconds: 1),
    );
    await login.login('android');
    expect(login.state, LoginState.timeoutUnresolved);
    expect(login.nativeFlowUnresolved, isTrue);
    expect(line.calls, 1);
    expect(api.calls, isEmpty);
  });

  test('timeout blocks reentry and late completion never exchanges', () async {
    final api = ScriptedTransport();
    final line = ControlledLine();
    final login = LoginCoordinator(
      line,
      api,
      SessionController(api, MemoryStore(), 'install', SecureIds()),
      SecureIds(),
      'install',
      loginTimeout: const Duration(milliseconds: 1),
    );

    await login.login('android');
    await login.login('android');
    expect(line.calls, 1);
    expect(login.state, LoginState.timeoutUnresolved);

    line.attempts.single.complete('late-obvious-fake-id-token');
    await pumpEventQueue();
    expect(login.state, LoginState.timeoutResolved);
    expect(login.nativeFlowUnresolved, isFalse);
    expect(api.calls, isEmpty);
  });

  test('expired callback is stale while native timeout lock remains', () async {
    final api = ScriptedTransport();
    final line = ControlledLine();
    final login = LoginCoordinator(
      line,
      api,
      SessionController(api, MemoryStore(), 'install', SecureIds()),
      SequenceIds(),
      'install',
      loginTimeout: const Duration(milliseconds: 1),
    );

    await login.login('android');
    await login.completeAttemptForTesting(
      attempt: 'expired-attempt',
      nonce: 'expired-nonce',
      token: 'late-obvious-fake-id-token',
      platform: 'android',
    );
    expect(login.state, LoginState.stale);
    expect(login.nativeFlowUnresolved, isTrue);
    expect(api.calls, isEmpty);

    line.attempts.single.complete('late-obvious-fake-id-token');
    await pumpEventQueue();
    expect(login.state, LoginState.timeoutResolved);
    expect(login.nativeFlowUnresolved, isFalse);
    expect(api.calls, isEmpty);
  });

  test(
    'confirmed late cancel permits exactly one fresh retry and exchange',
    () async {
      final api = ScriptedTransport()
        ..responses.add(
          ApiResponse(201, {
            'access_token': 'access',
            'refresh_token': 'refresh-token-with-at-least-32-characters',
            'session_id': 's',
            'expires_in': 900,
          }),
        );
      final line = ControlledLine();
      final login = LoginCoordinator(
        line,
        api,
        SessionController(api, MemoryStore(), 'install', SecureIds()),
        SecureIds(),
        'install',
        loginTimeout: const Duration(milliseconds: 1),
      );

      await login.login('android');
      line.attempts.single.completeError(PlatformException(code: 'CANCELLED'));
      await pumpEventQueue();
      expect(login.state, LoginState.cancelled);
      expect(login.nativeFlowUnresolved, isFalse);

      final retry = login.login('android');
      expect(line.calls, 2);
      line.attempts.last.complete('fresh-obvious-fake-id-token');
      await retry;
      expect(login.state, LoginState.authenticated);
      expect(api.calls, hasLength(1));
      expect(api.calls.single.$2, '/auth/line/exchange');
    },
  );

  test(
    'dispose suppresses notification after timed-out native completion',
    () async {
      final api = ScriptedTransport();
      final line = ControlledLine();
      final login = LoginCoordinator(
        line,
        api,
        SessionController(api, MemoryStore(), 'install', SecureIds()),
        SecureIds(),
        'install',
        loginTimeout: const Duration(milliseconds: 1),
      );
      var notifications = 0;
      login.addListener(() => notifications++);
      await login.login('android');
      login.dispose();
      final beforeCompletion = notifications;
      line.attempts.single.complete('late-obvious-fake-id-token');
      await pumpEventQueue();
      expect(notifications, beforeCompletion);
      expect(api.calls, isEmpty);
    },
  );

  test('unsupported native platform fails closed with zero calls', () async {
    final api = ScriptedTransport();
    final line = FakeLine();
    final login = LoginCoordinator(
      line,
      api,
      SessionController(api, MemoryStore(), 'install', SecureIds()),
      SecureIds(),
      'install',
    );
    await login.login('windows');
    expect(login.state, LoginState.unavailable);
    expect(line.calls, 0);
    expect(api.calls, isEmpty);
  });

  test('response stream timeout remains a NetworkException', () async {
    final transport = HttpApiTransport(
      Uri.parse('https://example.invalid'),
      MockClient.streaming(
        (_, __) async => http.StreamedResponse(
          Stream<List<int>>.error(TimeoutException('stream timeout')),
          200,
        ),
      ),
      timeout: const Duration(milliseconds: 5),
    );
    await expectLater(
      transport.send('GET', '/me'),
      throwsA(isA<NetworkException>()),
    );
  });

  test('stale and duplicate native completions never exchange twice', () async {
    final api = ScriptedTransport()
      ..responses.add(
        ApiResponse(201, {
          'access_token': 'access',
          'refresh_token': 'refresh-token-with-at-least-32-characters',
          'session_id': 's',
          'expires_in': 900,
        }),
      );
    final login = LoginCoordinator(
      FakeLine(),
      api,
      SessionController(api, MemoryStore(), 'install', SecureIds()),
      SecureIds(),
      'install',
    );
    await login.login('android');
    final body = api.calls.single.$4!;
    await login.completeAttemptForTesting(
      attempt: body['login_attempt_id'] as String,
      nonce: body['nonce'] as String,
      token: 'duplicate',
      platform: 'android',
    );
    expect(login.state, LoginState.duplicate);
    expect(api.calls, hasLength(1));
    await login.completeAttemptForTesting(
      attempt: 'different-attempt-id',
      nonce: 'different-nonce-value',
      token: 'stale',
      platform: 'android',
    );
    expect(login.state, LoginState.stale);
    expect(api.calls, hasLength(1));
  });

  test(
    'offline mutation is read-only and makes zero transport calls',
    () async {
      final transport = ScriptedTransport();
      final store = MemoryStore();
      final sessions = SessionController(
        transport,
        store,
        'install',
        SecureIds(),
      );
      final api = BasicApi(sessions, store, 'install', SecureIds());
      await expectLater(
        api.reply('g', AttendanceReply.attending, online: false),
        throwsA(isA<OfflineReadOnlyException>()),
      );
      expect(transport.calls, isEmpty);
      expect(store.values, isEmpty);
    },
  );

  test('uncertain mutation reconciles and removes durable intent', () async {
    final transport = ScriptedTransport()
      ..responses.addAll([
        const ApiResponse(503, null),
        ApiResponse(200, {
          'game_id': 'g',
          'own_reply': 'attending',
          'replied': [],
        }),
      ]);
    final store = MemoryStore();
    final sessions = SessionController(
      transport,
      store,
      'install',
      SecureIds(),
    );
    await sessions.accept(session('access', 'refresh'));
    final result = await BasicApi(
      sessions,
      store,
      'install',
      SecureIds(),
    ).reply('g', AttendanceReply.attending, online: true);
    expect(result.idempotentReplay, isTrue);
    expect(store.values.keys, isNot(contains('mutation:install:g')));
    expect(transport.calls[0].$3['Idempotency-Key'], isNotEmpty);
  });

  test(
    'PUT Network reconciles matching attendance and clears intent',
    () async {
      final transport = NetworkScriptTransport([
        const NetworkException(),
        ApiResponse(200, {
          'game_id': 'g',
          'own_reply': 'attending',
          'replied': [],
        }),
      ]);
      final store = MemoryStore();
      final sessions = SessionController(
        transport,
        store,
        'install',
        SecureIds(),
      );
      await sessions.accept(session('access', 'refresh'));
      final result = await BasicApi(
        sessions,
        store,
        'install',
        SecureIds(),
      ).reply('g', AttendanceReply.attending, online: true);
      expect(result.notification.code, 'outcome_unknown');
      expect(transport.calls.map((call) => call.$1), ['PUT', 'GET']);
      expect(store.values['mutation:install:g'], isNull);
    },
  );

  test(
    'pre-PUT refresh Network does not reconcile as mutation uncertain',
    () async {
      final transport = NetworkScriptTransport([const NetworkException()]);
      final store = MemoryStore()
        ..values['refresh:install'] =
            'refresh-token-with-at-least-32-characters';
      final sessions = SessionController(
        transport,
        store,
        'install',
        SecureIds(),
      );
      await expectLater(
        BasicApi(
          sessions,
          store,
          'install',
          SecureIds(),
        ).reply('g', AttendanceReply.attending, online: true),
        throwsA(isA<NetworkException>()),
      );
      expect(transport.calls.map((call) => (call.$1, call.$2)), [
        ('POST', '/auth/refresh'),
      ]);
      expect(store.values['mutation:install:g'], contains('attending'));
    },
  );

  test('PUT 401 then refresh Network does not attendance reconcile', () async {
    final transport = NetworkScriptTransport([
      const ApiResponse(401, null),
      const NetworkException(),
    ]);
    final store = MemoryStore();
    final sessions = SessionController(
      transport,
      store,
      'install',
      SecureIds(),
    );
    await sessions.accept(
      session('old-access', 'refresh-token-with-at-least-32-characters'),
    );
    await expectLater(
      BasicApi(
        sessions,
        store,
        'install',
        SecureIds(),
      ).reply('g', AttendanceReply.attending, online: true),
      throwsA(isA<NetworkException>()),
    );
    expect(transport.calls.map((call) => (call.$1, call.$2)), [
      ('PUT', '/games/g/attendance-reply'),
      ('POST', '/auth/refresh'),
    ]);
    expect(store.values['mutation:install:g'], contains('attending'));
  });

  test('PUT Network reconcile mismatch retains same intent and key', () async {
    final transport = NetworkScriptTransport([
      const NetworkException(),
      ApiResponse(200, {'game_id': 'g', 'own_reply': null, 'replied': []}),
    ]);
    final store = MemoryStore();
    final sessions = SessionController(
      transport,
      store,
      'install',
      SecureIds(),
    );
    await sessions.accept(session('access', 'refresh'));
    await expectLater(
      BasicApi(
        sessions,
        store,
        'install',
        SecureIds(),
      ).reply('g', AttendanceReply.attending, online: true),
      throwsA(isA<MutationUncertainException>()),
    );
    expect(transport.calls.map((call) => call.$1), ['PUT', 'GET']);
    final intent = store.values['mutation:install:g'];
    expect(intent, contains('attending'));
    expect(intent, contains(transport.calls.first.$3['Idempotency-Key']!));
  });

  test(
    'PUT Network and reconcile Network retain intent as uncertain',
    () async {
      final transport = NetworkScriptTransport([
        const NetworkException(),
        const NetworkException(),
      ]);
      final store = MemoryStore();
      final sessions = SessionController(
        transport,
        store,
        'install',
        SecureIds(),
      );
      await sessions.accept(session('access', 'refresh'));
      await expectLater(
        BasicApi(
          sessions,
          store,
          'install',
          SecureIds(),
        ).reply('g', AttendanceReply.attending, online: true),
        throwsA(isA<MutationUncertainException>()),
      );
      expect(transport.calls.map((call) => call.$1), ['PUT', 'GET']);
      final intent = store.values['mutation:install:g'];
      expect(intent, contains(transport.calls.first.$3['Idempotency-Key']!));
    },
  );

  test('explicit mutation error does not reconcile as uncertain', () async {
    final transport = NetworkScriptTransport([
      ApiResponse(409, apiError('idempotency_conflict')),
    ]);
    final store = MemoryStore();
    final sessions = SessionController(
      transport,
      store,
      'install',
      SecureIds(),
    );
    await sessions.accept(session('access', 'refresh'));
    await expectLater(
      BasicApi(
        sessions,
        store,
        'install',
        SecureIds(),
      ).reply('g', AttendanceReply.attending, online: true),
      throwsA(isA<ApiError>()),
    );
    expect(transport.calls.map((call) => call.$1), ['PUT']);
  });

  test('same uncertain logical reply reuses the idempotency key', () async {
    final transport = ScriptedTransport()
      ..responses.addAll([
        const ApiResponse(503, null),
        ApiResponse(200, {'game_id': 'g', 'own_reply': null, 'replied': []}),
        ApiResponse(200, mutationJson('attending')),
      ]);
    final store = MemoryStore();
    final sessions = SessionController(
      transport,
      store,
      'install',
      SecureIds(),
    );
    await sessions.accept(session('access', 'refresh'));
    final api = BasicApi(sessions, store, 'install', SecureIds());
    await expectLater(
      api.reply('g', AttendanceReply.attending, online: true),
      throwsA(isA<MutationUncertainException>()),
    );
    final firstKey = transport.calls.first.$3['Idempotency-Key'];
    await api.reply('g', AttendanceReply.attending, online: true);
    expect(transport.calls.last.$3['Idempotency-Key'], firstKey);
  });

  test(
    'different reply is blocked while uncertain intent mismatches',
    () async {
      final transport = ScriptedTransport()
        ..responses.add(
          ApiResponse(200, {'game_id': 'g', 'own_reply': null, 'replied': []}),
        );
      final store = MemoryStore()
        ..values['mutation:install:g'] =
            '{"key":"original-key-value","reply":"attending","uncertain":true}';
      final sessions = SessionController(
        transport,
        store,
        'install',
        SecureIds(),
      );
      await sessions.accept(session('access', 'refresh'));
      await expectLater(
        BasicApi(
          sessions,
          store,
          'install',
          SecureIds(),
        ).reply('g', AttendanceReply.notAttending, online: true),
        throwsA(isA<MutationPendingException>()),
      );
      expect(transport.calls, hasLength(1));
      expect(transport.calls.single.$1, 'GET');
      expect(store.values['mutation:install:g'], contains('attending'));
    },
  );

  test('confirmed old intent permits new reply with a new key', () async {
    final transport = ScriptedTransport()
      ..responses.addAll([
        ApiResponse(200, {
          'game_id': 'g',
          'own_reply': 'attending',
          'replied': [],
        }),
        ApiResponse(200, mutationJson('not_attending')),
      ]);
    final store = MemoryStore()
      ..values['mutation:install:g'] =
          '{"key":"original-key-value","reply":"attending","uncertain":true}';
    final sessions = SessionController(
      transport,
      store,
      'install',
      SecureIds(),
    );
    await sessions.accept(session('access', 'refresh'));
    await BasicApi(
      sessions,
      store,
      'install',
      SecureIds(),
    ).reply('g', AttendanceReply.notAttending, online: true);
    expect(
      transport.calls.last.$3['Idempotency-Key'],
      isNot('original-key-value'),
    );
  });

  test('games follows canonical next_cursor until null', () async {
    final transport = ScriptedTransport()
      ..responses.addAll([
        ApiResponse(200, {
          'items': [gameJson('g1')],
          'next_cursor': 'next',
        }),
        ApiResponse(200, {
          'items': [gameJson('g2')],
          'next_cursor': null,
        }),
      ]);
    final sessions = SessionController(
      transport,
      MemoryStore(),
      'install',
      SecureIds(),
    );
    await sessions.accept(session('access', 'refresh'));
    final games = await BasicApi(
      sessions,
      MemoryStore(),
      'install',
      SecureIds(),
    ).games();
    expect(games.map((game) => game.id), ['g1', 'g2']);
    expect(transport.calls.last.$2, '/games?cursor=next');
  });

  test('cache is versioned, installation partitioned, and typed', () async {
    final store = MemoryStore();
    final cache = BasicCache(store, 'install-a');
    final at = DateTime.utc(2026, 8, 18, 12);
    await cache.save(
        const Person('p', 'Basic', ['games:read']),
        [
          Game('g', at, 60, null, null, null),
        ],
        at);
    final loaded = await cache.load();
    expect(loaded!.person.displayName, 'Basic');
    expect(loaded.games.single.id, 'g');
    expect(loaded.lastSyncedAt, at);
    expect(await BasicCache(MemoryStore(), 'install-b').load(), isNull);
    expect(store.values.keys, everyElement(contains('install-a')));
  });

  test(
    'cache/session aggregate accepts only complete bounded observations',
    () {
      expect(
        CacheSessionAggregate.resolve(
          sessionPresent: false,
          basicCachePresent: false,
          officerReportCachePresent: false,
          pendingAttendanceIntentCount: 0,
        ),
        const CacheSessionAggregate(
          sessionPresent: false,
          basicCachePresent: false,
          officerReportCachePresent: false,
          pendingAttendanceIntentPresent: false,
        ),
      );
      expect(
        CacheSessionAggregate.resolve(
          sessionPresent: true,
          basicCachePresent: true,
          officerReportCachePresent: true,
          pendingAttendanceIntentCount: 1,
        ),
        const CacheSessionAggregate(
          sessionPresent: true,
          basicCachePresent: true,
          officerReportCachePresent: true,
          pendingAttendanceIntentPresent: true,
        ),
      );
    },
  );

  test(
    'cache/session aggregate fails closed for missing or inconsistent state',
    () {
      expect(
        CacheSessionAggregate.resolve(
          sessionPresent: null,
          basicCachePresent: false,
          officerReportCachePresent: false,
          pendingAttendanceIntentCount: 0,
        ),
        isNull,
      );
      expect(
        CacheSessionAggregate.resolve(
          sessionPresent: false,
          basicCachePresent: false,
          officerReportCachePresent: false,
          pendingAttendanceIntentCount: 2,
        ),
        isNull,
      );
    },
  );

  test('notification destinations are typed and fail safely to the list', () {
    const notificationId = 'notification_41';
    final notification = NotificationDestination.parseOrFallback({
      'type': 'notification',
      'notification_id': notificationId,
    }, notificationId);
    final game = NotificationDestination.parseOrFallback({
      'type': 'game',
      'game_id': 'game_-112001',
    }, notificationId);
    final unknown = NotificationDestination.parseOrFallback({
      'type': 'url',
      'url': 'https://example.invalid/private',
    }, notificationId);
    final minimum = NotificationDestination.parseOrFallback({
      'type': 'game',
      'game_id': 'game_-9223372036854775808',
    }, notificationId);
    final malformed = [
      {
        'type': 'notification',
        'notification_id': notificationId,
        'extra': true,
      },
      {'type': 'game', 'game_id': 'game_01'},
      {'type': 'game', 'game_id': 'game_-9223372036854775809'},
      {'type': 'game', 'game_id': 'game_9223372036854775808'},
      {
        'type': 'game',
        'game_id': 'game_1',
        'url': 'https://example.invalid',
      },
    ].map(
      (value) => NotificationDestination.parseOrFallback(value, notificationId),
    );
    expect(
      notification.safeRoute(notificationVisible: true),
      '/notifications/notification_41',
    );
    expect(
      game.safeRoute(
        notificationVisible: true,
        authorizedGameIds: const {'game_-112001'},
      ),
      '/games/game_-112001',
    );
    expect(game.safeRoute(notificationVisible: true), '/notifications');
    expect(unknown.safeRoute(notificationVisible: true), '/notifications');
    expect(
      minimum.safeRoute(
        notificationVisible: true,
        authorizedGameIds: const {'game_-9223372036854775808'},
      ),
      '/games/game_-9223372036854775808',
    );
    for (final destination in malformed) {
      expect(
        destination.safeRoute(notificationVisible: true),
        '/notifications',
      );
    }
    expect(
      notification.safeRoute(notificationVisible: false),
      '/notifications',
    );
  });

  test(
    'basic publishing fails locally with zero recipient or transport access',
    () async {
      final transport = ScriptedTransport();
      final sessions = SessionController(
        transport,
        MemoryStore(),
        'installation',
        SecureIds(),
      );
      await sessions.accept(session('access', 'refresh'));
      final publisher = OfficerNotificationPublisher(
        sessions,
        const Person('person_1', 'Basic', [
          'games:read',
          'attendance:reply:self',
          'notifications:read',
        ]),
      );
      await expectLater(
        publisher.preview(const {}),
        throwsA(isA<ContractException>()),
      );
      expect(transport.calls, isEmpty);
    },
  );

  test(
    'officer publishing carries exact revision confirmation and key',
    () async {
      final revision = List.filled(64, 'a').join();
      final transport = ScriptedTransport()
        ..responses.addAll([
          ApiResponse(200, {
            'recipient_count': 2,
            'revision': revision,
            'confirmation_text': 'PUBLISH 2',
          }),
          ApiResponse(201, {
            'notification_id': 'notification_81',
            'recipient_count': 2,
            'deliveries': const [],
            'idempotent_replay': false,
          }),
        ]);
      final sessions = SessionController(
        transport,
        MemoryStore(),
        'installation',
        SecureIds(),
      );
      await sessions.accept(session('access', 'refresh'));
      final publisher = OfficerNotificationPublisher(
        sessions,
        const Person(
            'person_1',
            'Officer',
            [
              'games:read',
              'attendance:reply:self',
              'notifications:read',
              'attendance:report:read',
              'notifications:publish',
            ],
            accessLevel: AccessLevel.officer),
      );
      final draft = <String, dynamic>{
        'type': 'officer_team_broadcast',
        'title': '集合提醒',
        'body': '請準時抵達。',
        'audience': {'type': 'team'},
        'destination': {'type': 'notification'},
      };
      final preview = await publisher.preview(draft);
      await publisher.confirm(draft, preview, 'publish-command-0001');
      expect(transport.calls[1].$3['Idempotency-Key'], 'publish-command-0001');
      expect(transport.calls[1].$4!['preview_revision'], revision);
      expect(transport.calls[1].$4!['typed_confirmation'], 'PUBLISH 2');
    },
  );
}
