import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/foundation.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/main.dart' as entrypoint;

class QueueTransport implements ApiTransport {
  final List<ApiResponse> responses = [];
  final List<(String, String, Map<String, String>, Map<String, dynamic>?)>
      calls = [];
  Completer<void>? mutationGate;
  bool networkOnPut = false;
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    calls.add((method, path, headers, body));
    if (method == 'PUT' && networkOnPut) {
      networkOnPut = false;
      throw const NetworkException();
    }
    if (method == 'PUT' && mutationGate != null) {
      await mutationGate!.future;
    }
    return responses.removeAt(0);
  }
}

Map<String, dynamic> gameJson() => {
      'id': 'g',
      'start_at': '2026-08-18T12:00:00Z',
      'duration_minutes': 60,
      'location': '球場',
      'home_team': 'Home',
      'away_team': 'Away'
    };

Map<String, dynamic> attendanceJson() => {
      'game_id': 'g',
      'own_reply': 'undecided',
      'replied': [
        {
          'person_id': 'p2',
          'display_name': '已回覆隊員',
          'reply': 'attending',
          'qualification': 'team_player'
        }
      ]
    };

Map<String, dynamic> errorJson(String code) => {
      'error': {
        'code': code,
        'message': 'safe',
        'request_id': 'request',
        'retryable': false,
        'retry_after_seconds': null,
        'field_errors': []
      }
    };

Map<String, dynamic> mutationJson() => {
      'game_id': 'g',
      'reply': 'attending',
      'changed': true,
      'updated_at': '2026-08-18T12:00:00Z',
      'notification': {'status': 'not_required', 'code': null},
      'idempotent_replay': false
    };

Future<BasicApi> apiFor(QueueTransport transport, MemoryStore store) async {
  final session = SessionController(transport, store, 'install', SecureIds());
  await session.accept(const SessionEnvelope(
      accessToken: 'access',
      refreshToken: 'refresh-token-with-at-least-32-characters',
      sessionId: 's',
      expiresIn: 900));
  return BasicApi(session, store, 'install', SecureIds());
}

void main() {
  for (final state in AuthViewState.values) {
    testWidgets('$state has distinguishable semantics', (tester) async {
      await tester.pumpWidget(MaterialApp(home: AuthStatePanel(state: state)));
      expect(find.bySemanticsLabel(RegExp('.+')), findsWidgets);
      if (state == AuthViewState.booting || state == AuthViewState.exchanging) {
        expect(find.byType(CircularProgressIndicator), findsOneWidget);
      }
    });
  }

  testWidgets('unresolved native timeout hides login action', (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
            body: AuthStatePanel(state: AuthViewState.timeoutUnresolved),
            floatingActionButton: LoginActionButton(
                state: AuthViewState.timeoutUnresolved, onLogin: null))));
    expect(find.text('LINE 登入已逾時，請關閉既有登入畫面後返回'), findsOneWidget);
    expect(find.byTooltip('LINE 登入'), findsNothing);
  });

  testWidgets('confirmed cancellation re-enables one login action',
      (tester) async {
    var calls = 0;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            floatingActionButton: LoginActionButton(
                state: AuthViewState.cancelled, onLogin: () => calls++))));
    expect(find.byTooltip('LINE 登入'), findsOneWidget);
    await tester.tap(find.byTooltip('LINE 登入'));
    expect(calls, 1);
  });

  test('fake versus real composition selects separate roots', () {
    final fake = entrypoint
        .composeRoot(AppConfig.parse(flavor: 'development', mode: 'fake'));
    final real = entrypoint.composeRoot(AppConfig.parse(
        flavor: 'staging',
        mode: 'real',
        apiBaseUrl: 'https://example.invalid',
        lineChannelId: '123'));
    expect(fake, isA<DemoApp>());
    expect(real, isA<BasicBootstrapApp>());
  });

  test('only recoverable network plus cache becomes offline', () {
    expect(classifyFailure(const NetworkException(), hasCache: true),
        AuthViewState.offline);
    expect(classifyFailure(const NetworkException(), hasCache: false),
        AuthViewState.recoverableError);
    expect(classifyFailure(const ContractException('bad'), hasCache: true),
        AuthViewState.contractError);
    expect(classifyFailure(const SessionExpiredException(), hasCache: true),
        AuthViewState.sessionExpired);
  });

  test('native platform mapping accepts only Android and iOS', () {
    expect(nativePlatformName(TargetPlatform.android), 'android');
    expect(nativePlatformName(TargetPlatform.iOS), 'ios');
    expect(nativePlatformName(TargetPlatform.windows), isNull);
    expect(nativePlatformName(TargetPlatform.linux), isNull);
    expect(nativePlatformName(TargetPlatform.macOS), isNull);
    expect(nativePlatformName(TargetPlatform.fuchsia), isNull);
  });

  testWidgets('Basic-only navigation exposes games and no management',
      (tester) async {
    final transport = QueueTransport();
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(MaterialApp(
        home: BasicGamesView(
            api: api,
            person: const Person('p', 'Basic', ['games:read']),
            games: [Game('g', DateTime.utc(2026), 60, null, 'Home', 'Away')],
            online: true,
            lastSyncedAt: DateTime.utc(2026))));
    expect(find.byKey(const ValueKey('game-g')), findsOneWidget);
    expect(find.text('管理'), findsNothing);
    expect(find.text('系統公告'), findsNothing);
  });

  testWidgets('server report grant exposes only the read-only management route',
      (tester) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(MaterialApp(
        home: BasicGamesView(
            api: api,
            person: const Person(
                'p', 'Officer', ['games:read', 'attendance:report:read'],
                accessLevel: AccessLevel.officer),
            games: [Game('g', DateTime.utc(2026), 60, null, 'Home', 'Away')],
            online: true,
            lastSyncedAt: DateTime.utc(2026))));
    expect(
        find.byKey(const ValueKey('management-report-entry')), findsOneWidget);
    expect(find.text('通知廣播'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('management-report-entry')));
    await tester.pumpAndSettle();
    expect(find.text('出席報表'), findsOneWidget);
    expect(find.text('唯讀出席報表'), findsOneWidget);
    expect(find.text('送出回覆'), findsNothing);
  });

  testWidgets('offline Basic list disables detail and attendance reply',
      (tester) async {
    final transport = QueueTransport();
    final api = await apiFor(transport, MemoryStore());
    await tester.pumpWidget(MaterialApp(
        home: BasicGamesView(
            api: api,
            person: const Person('p', 'Basic', ['games:read']),
            games: [Game('g', DateTime.utc(2026), 60, null, 'Home', 'Away')],
            online: false,
            lastSyncedAt: DateTime.utc(2026))));
    final offline = find.byKey(const ValueKey('offline-read-only'));
    expect(offline, findsOneWidget);
    expect(tester.getSemantics(offline).label, contains('離線唯讀'));
    await tester.tap(find.byKey(const ValueKey('game-g')));
    await tester.pump();
    expect(find.text('賽事與出席'), findsNothing);
    expect(transport.calls, isEmpty);
  });

  testWidgets('empty games has recognizable read-state semantics',
      (tester) async {
    final api = await apiFor(QueueTransport(), MemoryStore());
    await tester.pumpWidget(MaterialApp(
        home: BasicGamesView(
            api: api,
            person: const Person('p', 'Basic', ['games:read']),
            games: const [],
            online: true,
            lastSyncedAt: DateTime.utc(2026))));
    final empty = find.byKey(const ValueKey('games-empty'));
    expect(empty, findsOneWidget);
    expect(tester.getSemantics(empty).label, contains('目前沒有可顯示的賽事'));
  });

  testWidgets('game detail reads attendance and exposes five reply controls',
      (tester) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester
        .pumpWidget(MaterialApp(home: GameDetailPage(api: api, gameId: 'g')));
    await tester.pumpAndSettle();
    expect(find.text('已回覆隊員'), findsNWidgets(2));
    expect(find.text('未回覆'), findsNothing);
    for (final reply in AttendanceReply.values) {
      expect(find.byKey(ValueKey('reply-${reply.wire}')), findsOneWidget);
    }
  });

  testWidgets('uncertain conflicting reply has recognizable UX',
      (tester) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
        ApiResponse(
            200, {'game_id': 'g', 'own_reply': 'undecided', 'replied': []}),
      ]);
    final store = MemoryStore()
      ..values['mutation:install:g'] =
          '{"key":"same-key-value-1234","reply":"attending","uncertain":true}';
    final api = await apiFor(transport, store);
    await tester
        .pumpWidget(MaterialApp(home: GameDetailPage(api: api, gameId: 'g')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reply-not_attending')));
    await tester.tap(find.text('送出回覆'));
    await tester.pumpAndSettle();
    final uncertain = find.byKey(const ValueKey('mutation-uncertain'));
    expect(uncertain, findsOneWidget);
    expect(tester.getSemantics(uncertain).label, contains('回覆結果待確認'));
  });

  testWidgets('PUT Network ambiguity displays uncertain instead of error',
      (tester) async {
    final transport = QueueTransport()
      ..networkOnPut = true
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
        ApiResponse(200, {'game_id': 'g', 'own_reply': null, 'replied': []}),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester
        .pumpWidget(MaterialApp(home: GameDetailPage(api: api, gameId: 'g')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reply-attending')));
    await tester.tap(find.text('送出回覆'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('mutation-uncertain')), findsOneWidget);
    expect(find.byKey(const ValueKey('mutation-error')), findsNothing);
    expect(
        transport.calls.map((call) => call.$1), ['GET', 'GET', 'PUT', 'GET']);
  });

  testWidgets('mutation pending disables submit then returns ready',
      (tester) async {
    final gate = Completer<void>();
    final transport = QueueTransport()
      ..mutationGate = gate
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
        ApiResponse(200, mutationJson()),
        ApiResponse(200, attendanceJson()),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester
        .pumpWidget(MaterialApp(home: GameDetailPage(api: api, gameId: 'g')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reply-attending')));
    await tester.tap(find.text('送出回覆'));
    await tester.pump();
    expect(find.text('送出中'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNull);
    gate.complete();
    await tester.pumpAndSettle();
    expect(find.text('送出回覆'), findsOneWidget);
  });

  testWidgets('canonical mutation error has fail-closed UX', (tester) async {
    final transport = QueueTransport()
      ..responses.addAll([
        ApiResponse(200, gameJson()),
        ApiResponse(200, attendanceJson()),
        ApiResponse(409, errorJson('idempotency_conflict')),
      ]);
    final api = await apiFor(transport, MemoryStore());
    await tester
        .pumpWidget(MaterialApp(home: GameDetailPage(api: api, gameId: 'g')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reply-attending')));
    await tester.tap(find.text('送出回覆'));
    await tester.pumpAndSettle();
    final error = find.byKey(const ValueKey('mutation-error'));
    expect(error, findsOneWidget);
    expect(tester.getSemantics(error).label, contains('出席回覆失敗'));
  });
}
