import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ntubtob_portal/account_deletion.dart';
import 'package:ntubtob_portal/foundation.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/production_demo.dart';
import 'package:ntubtob_portal/support_app_info.dart';

const _id = '00000000-0000-4000-8000-000000000001';
final _receipt = AccountDeletionReceipt(_id, DateTime.utc(2035, 1, 1));
Map<String, dynamic> _envelope() => {
      'request': {
        'id': _id,
        'status': 'requested',
        'requested_at': '2035-01-01T00:00:00Z',
      },
    };

const _session = SessionEnvelope(
  accessToken: 'fictional-access',
  refreshToken: 'fictional-refresh-token-with-at-least-32-characters',
  sessionId: 'fictional-session',
  expiresIn: 900,
);

class _Port extends ChangeNotifier implements AccountDeletionPort {
  @override
  Listenable get changes => this;
  bool get subscribed => hasListeners;
  @override
  bool online = true;
  bool current = true;
  int reads = 0, requests = 0;
  bool uncertain = false;
  bool readFailure = false;
  AccountDeletionReceipt? receipt;
  Completer<AccountDeletionReceipt?>? delayedRead;

  @override
  void requireCurrent() {
    if (!current) throw const SessionSupersededException();
  }

  void _check() {
    requireCurrent();
    if (!online) throw const OfflineReadOnlyException();
  }

  @override
  Future<AccountDeletionReceipt?> read() async {
    _check();
    reads++;
    if (readFailure) throw const AccountDeletionUnavailable();
    if (delayedRead != null) return delayedRead!.future;
    return receipt;
  }

  @override
  Future<AccountDeletionReceipt> request({required bool confirmed}) async {
    _check();
    expect(confirmed, isTrue);
    requests++;
    receipt ??= _receipt;
    if (uncertain) throw const AccountDeletionOutcomeUncertain();
    return receipt!;
  }
}

Future<void> _show(WidgetTester tester, AccountDeletionPort port) async {
  await tester.pumpWidget(MaterialApp(home: AccountDeletionPage(client: port)));
  await tester.pumpAndSettle();
}

void main() {
  test('receipt accepts only a requested receipt or explicit null', () {
    expect(AccountDeletionReceipt.parse({'request': null}), isNull);
    final receipt = AccountDeletionReceipt.parse(_envelope())!;
    expect(receipt.id, _id);
    expect(receipt.requestedAt, DateTime.utc(2035, 1, 1));
    for (final value in <Map<String, dynamic>?>[
      null,
      {},
      {'request': null, 'person_id': 'must-not-be-projected'},
      {'request': []},
      {
        'request': {...(_envelope()['request'] as Map), 'status': 'deleted'}
      },
      {
        'request': {...(_envelope()['request'] as Map), 'id': 'not-a-uuid'}
      },
      {
        'request': {
          ...(_envelope()['request'] as Map),
          'requested_at': '2035-01-01'
        }
      },
      {
        'request': {
          ...(_envelope()['request'] as Map),
          'requested_at': '2035-02-31T00:00:00Z'
        }
      },
      {
        'request': {
          ...(_envelope()['request'] as Map),
          'requested_at': '2035-01-01T24:00:00Z'
        }
      },
      {
        'request': {...(_envelope()['request'] as Map), 'id': '$_id\n'}
      },
      {
        'request': {
          ...(_envelope()['request'] as Map),
          'secret': 'must-not-render'
        }
      },
    ]) {
      // Match the runtime map types produced by the HTTP JSON decoder.
      final decoded = jsonDecode(jsonEncode(value)) as Map<String, dynamic>?;
      expect(() => AccountDeletionReceipt.parse(decoded),
          throwsA(isA<ContractException>()));
    }
  });

  test('HTTP client is exact self scope, fixed body and stable request key',
      () async {
    final requests = <http.Request>[];
    final httpClient = MockClient((request) async {
      requests.add(request);
      return http.Response(
          jsonEncode(_envelope()), request.method == 'GET' ? 200 : 202);
    });
    addTearDown(httpClient.close);
    final session = SessionController(
      HttpApiTransport(Uri.parse('https://example.invalid'), httpClient),
      MemoryStore(),
      'fixture',
      SecureIds(),
    );
    await session.accept(_session);
    final client = AccountDeletionClient(session,
        isOnline: () => true, requestId: () => _id);
    expect((await client.read())!.id, _id);
    expect((await client.request(confirmed: true)).id, _id);
    expect((await client.request(confirmed: true)).id, _id);
    expect(requests, hasLength(3));
    for (final request in requests) {
      expect(request.url.path, '/api/v1/me/account-deletion');
      expect(request.url.query, isEmpty);
      expect(request.headers['Authorization'], 'Bearer fictional-access');
    }
    for (final request in requests.where((r) => r.method == 'POST')) {
      expect(jsonDecode(request.body), {'confirmed': true});
      expect(request.headers['Idempotency-Key'], _id);
    }
  });

  test('offline, unconfirmed and superseded requests never reach transport',
      () async {
    var calls = 0;
    final httpClient = MockClient((_) async {
      calls++;
      return http.Response('{}', 500);
    });
    addTearDown(httpClient.close);
    final session = SessionController(
      HttpApiTransport(Uri.parse('https://example.invalid'), httpClient),
      MemoryStore(),
      'fixture',
      SecureIds(),
    );
    await session.accept(_session);
    var online = false;
    final client = AccountDeletionClient(session, isOnline: () => online);
    await expectLater(client.read(), throwsA(isA<OfflineReadOnlyException>()));
    await expectLater(client.request(confirmed: true),
        throwsA(isA<OfflineReadOnlyException>()));
    online = true;
    await expectLater(client.request(confirmed: false), throwsArgumentError);
    await session.clear();
    await expectLater(
        client.read(), throwsA(isA<SessionSupersededException>()));
    await expectLater(client.request(confirmed: true),
        throwsA(isA<SessionSupersededException>()));
    expect(calls, 0);
  });

  for (final response in [
    http.Response('{}', 503),
    http.Response('{"request":null}', 202),
    http.Response(
        jsonEncode({
          'request': {'status': 'deleted'}
        }),
        202),
  ]) {
    test('ambiguous POST ${response.statusCode}/${response.body} never retries',
        () async {
      var calls = 0;
      final httpClient = MockClient((_) async {
        calls++;
        return response;
      });
      addTearDown(httpClient.close);
      final session = SessionController(
        HttpApiTransport(Uri.parse('https://example.invalid'), httpClient),
        MemoryStore(),
        'fixture',
        SecureIds(),
      );
      await session.accept(_session);
      final client = AccountDeletionClient(session, isOnline: () => true);
      await expectLater(client.request(confirmed: true),
          throwsA(isA<AccountDeletionOutcomeUncertain>()));
      expect(calls, 1);
    });
  }

  testWidgets('opening and cancelling only read, confirmation records intent',
      (tester) async {
    final port = _Port();
    await _show(tester, port);
    expect(port.reads, 1);
    expect(port.requests, 0);
    await tester.tap(find.byKey(const ValueKey('request-account-deletion')));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(port.requests, 0);
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();
    expect(port.requests, 0);
    await tester.tap(find.byKey(const ValueKey('request-account-deletion')));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('confirm-account-deletion-request')));
    await tester.pumpAndSettle();
    expect(port.requests, 1);
    expect(find.text('申請已記錄；帳號與資料尚未刪除'), findsOneWidget);
    expect(
        find.byKey(const ValueKey('request-account-deletion')), findsNothing);
    await tester.pumpWidget(const SizedBox());
    await _show(tester, port);
    expect(port.reads, 2);
    expect(port.requests, 1);
  });

  testWidgets('uncertain submission only reconciles through a manual GET',
      (tester) async {
    final port = _Port()..uncertain = true;
    await _show(tester, port);
    await tester.tap(find.byKey(const ValueKey('request-account-deletion')));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('confirm-account-deletion-request')));
    await tester.pumpAndSettle();
    expect(port.requests, 1);
    expect(port.reads, 1);
    expect(find.textContaining('送出結果尚未確認'), findsOneWidget);
    expect(
        find.byKey(const ValueKey('request-account-deletion')), findsNothing);
    await tester
        .tap(find.byKey(const ValueKey('read-account-deletion-status')));
    await tester.pumpAndSettle();
    expect(port.requests, 1);
    expect(port.reads, 2);
    expect(find.text('申請已記錄；帳號與資料尚未刪除'), findsOneWidget);
  });

  testWidgets('uncertain provenance survives failed then empty reconciliation',
      (tester) async {
    final port = _Port()..uncertain = true;
    await _show(tester, port);
    await tester.tap(find.byKey(const ValueKey('request-account-deletion')));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('confirm-account-deletion-request')));
    await tester.pumpAndSettle();
    port.readFailure = true;
    await tester
        .tap(find.byKey(const ValueKey('read-account-deletion-status')));
    await tester.pumpAndSettle();
    port.readFailure = false;
    port.receipt = null;
    await tester
        .tap(find.byKey(const ValueKey('read-account-deletion-status')));
    await tester.pumpAndSettle();
    expect(find.textContaining('不代表前次送出一定沒有發生'), findsOneWidget);
    expect(port.requests, 1);
    expect(port.reads, 3);
  });

  testWidgets('invalidation clears settled receipt and detaches old client',
      (tester) async {
    final port = _Port()..receipt = _receipt;
    await _show(tester, port);
    expect(find.textContaining('申請時間'), findsOneWidget);
    port.current = false;
    port.notifyListeners();
    await tester.pumpAndSettle();
    expect(find.textContaining('申請時間'), findsNothing);
    expect(find.textContaining('登入狀態已變更'), findsOneWidget);
    final next = _Port();
    await _show(tester, next);
    expect(port.subscribed, isFalse);
    expect(next.subscribed, isTrue);
    port.notifyListeners();
    await tester.pumpAndSettle();
    expect(find.text('目前沒有刪除申請'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    expect(next.subscribed, isFalse);
  });

  testWidgets('real client clears receipt immediately when session changes',
      (tester) async {
    final httpClient =
        MockClient((_) async => http.Response(jsonEncode(_envelope()), 200));
    addTearDown(httpClient.close);
    final session = SessionController(
      HttpApiTransport(Uri.parse('https://example.invalid'), httpClient),
      MemoryStore(),
      'fixture',
      SecureIds(),
    );
    await session.accept(_session);
    await _show(tester, AccountDeletionClient(session, isOnline: () => true));
    expect(find.textContaining('申請時間'), findsOneWidget);
    await session.clear();
    await tester.pumpAndSettle();
    expect(find.textContaining('申請時間'), findsNothing);
    expect(find.textContaining('登入狀態已變更'), findsOneWidget);
  });

  test('late real POST receipt is rejected after a new session', () async {
    final response = Completer<http.Response>();
    var calls = 0;
    final httpClient = MockClient((_) {
      calls++;
      return response.future;
    });
    addTearDown(httpClient.close);
    final session = SessionController(
      HttpApiTransport(Uri.parse('https://example.invalid'), httpClient),
      MemoryStore(),
      'fixture',
      SecureIds(),
    );
    await session.accept(_session);
    final client = AccountDeletionClient(session, isOnline: () => true);
    final result = client.request(confirmed: true);
    final rejected =
        expectLater(result, throwsA(isA<SessionSupersededException>()));
    await pumpEventQueue();
    await session.accept(_session);
    response.complete(http.Response(jsonEncode(_envelope()), 202));
    await rejected;
    expect(calls, 1);
  });

  testWidgets('invalidation during read never restores a late receipt',
      (tester) async {
    final port = _Port()..delayedRead = Completer<AccountDeletionReceipt?>();
    await tester
        .pumpWidget(MaterialApp(home: AccountDeletionPage(client: port)));
    await tester.pump();
    port.current = false;
    port.notifyListeners();
    await tester.pump();
    expect(find.textContaining('登入狀態已變更'), findsOneWidget);
    port.delayedRead!.complete(_receipt);
    await tester.pumpAndSettle();
    expect(find.textContaining('申請時間'), findsNothing);
    expect(find.textContaining('登入狀態已變更'), findsOneWidget);
  });

  testWidgets('invalidation while confirming cannot submit the old account',
      (tester) async {
    final port = _Port();
    await _show(tester, port);
    await tester.tap(find.byKey(const ValueKey('request-account-deletion')));
    await tester.pumpAndSettle();
    port.current = false;
    port.notifyListeners();
    await tester.pump();
    await tester
        .tap(find.byKey(const ValueKey('confirm-account-deletion-request')));
    await tester.pumpAndSettle();
    expect(port.requests, 0);
    expect(find.textContaining('登入狀態已變更'), findsOneWidget);
  });

  for (final offline in [true, false]) {
    testWidgets('confirmation rechecks ${offline ? 'online' : 'account'} state',
        (tester) async {
      final port = _Port();
      await _show(tester, port);
      await tester.tap(find.byKey(const ValueKey('request-account-deletion')));
      await tester.pumpAndSettle();
      if (offline) {
        port.online = false;
      } else {
        port.current = false;
      }
      await tester
          .tap(find.byKey(const ValueKey('confirm-account-deletion-request')));
      await tester.pumpAndSettle();
      expect(port.requests, 0);
      expect(find.textContaining(offline ? '離線唯讀' : '登入狀態已變更'), findsOneWidget);
    });
  }

  testWidgets('late receipt from a replaced client is not rendered',
      (tester) async {
    final old = _Port()..delayedRead = Completer<AccountDeletionReceipt?>();
    await tester
        .pumpWidget(MaterialApp(home: AccountDeletionPage(client: old)));
    await tester.pump();
    final current = _Port();
    await _show(tester, current);
    old.delayedRead!.complete(_receipt);
    await tester.pumpAndSettle();
    expect(find.text('目前沒有刪除申請'), findsOneWidget);
    expect(find.textContaining('申請時間'), findsNothing);
  });

  testWidgets('real default support does not expose an unconfigured intake',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: SupportAppInfoPage()));
    expect(find.byKey(const ValueKey('account-deletion-status-entry')),
        findsNothing);
    expect(
        find.byKey(const ValueKey('request-account-deletion')), findsNothing);
  });

  testWidgets('fictional demo runs request/status with zero transport calls',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final probe = ProductionDemoProbe()..deletionOutcomeUncertain = true;
    await tester.pumpWidget(ProductionDemoApp(
        flavor: const FlavorConfig(AppFlavor.development), probe: probe));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('demo-account-deletion')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('request-account-deletion')));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('confirm-account-deletion-request')));
    await tester.pumpAndSettle();
    expect(find.textContaining('送出結果尚未確認'), findsOneWidget);
    await tester
        .tap(find.byKey(const ValueKey('read-account-deletion-status')));
    await tester.pumpAndSettle();
    expect(find.text('申請已記錄；帳號與資料尚未刪除'), findsOneWidget);
    expect(probe.deletionRequests, 1);
    expect(probe.deletionReads, 2);
    expect(probe.unexpectedTransportCalls, 0);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('demo-persona-officer')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('demo-account-deletion')));
    await tester.pumpAndSettle();
    expect(find.text('目前沒有刪除申請'), findsOneWidget);
    expect(find.textContaining('申請時間'), findsNothing);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('demo-persona-basic')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('demo-account-deletion')));
    await tester.pumpAndSettle();
    expect(find.text('申請已記錄；帳號與資料尚未刪除'), findsOneWidget);
    expect(probe.deletionRequests, 1);
    expect(probe.unexpectedTransportCalls, 0);
  });
}
