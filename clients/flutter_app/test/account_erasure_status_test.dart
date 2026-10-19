import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_status.dart';

const id = '11111111-1111-4111-8111-111111111111';
Map<String, dynamic> envelope([String status = 'requested']) => {
      'id': id,
      'status': status,
      'requested_at': '2035-01-01T00:00:00+00:00',
      'updated_at': '2035-01-01T00:00:01.123456+00:00',
    };

class Reader extends ChangeNotifier implements AccountErasureStatusPort {
  @override
  Listenable get changes => this;
  @override
  bool online = true;
  @override
  String jobId = id;
  bool current = true;
  int calls = 0;
  Future<Map<String, dynamic>> Function() response = () async => envelope();
  @override
  void requireCurrent() {
    if (!current) throw StateError('private-secret-sentinel');
  }

  @override
  Future<Map<String, dynamic>> read() {
    calls++;
    return response();
  }

  void changed() => notifyListeners();
}

Widget page(Reader reader) =>
    MaterialApp(home: AccountErasureStatusPage(reader: reader));

void main() {
  test('rejects unknown envelope', () {
    expect(() => AccountErasureStatus.parse({}), throwsFormatException);
  });
  test('strict fields dates state and order', () {
    for (final change in [
      {'extra': true},
      {'status': 'future'},
      {'id': 'secret-sentinel'},
      {'requested_at': '2035-02-30T00:00:00Z'},
      {'updated_at': '2034-01-01T00:00:00Z'},
      {'updated_at': '2035-01-01T00:00:00'},
      {'updated_at': '2035-01-01T00:00:00+08:00'},
      {'updated_at': null},
    ]) {
      expect(() => AccountErasureStatus.parse({...envelope(), ...change}),
          throwsFormatException);
    }
    for (final state in AccountErasureStatus.messages.keys) {
      expect(AccountErasureStatus.parse(envelope(state)).status, state);
    }
  });
  testWidgets('all statuses truthful without identifiers or actions',
      (tester) async {
    for (final state in AccountErasureStatus.messages.keys) {
      final reader = Reader()..response = (() async => envelope(state));
      await tester.pumpWidget(page(reader));
      await tester.pumpAndSettle();
      expect(find.text(AccountErasureStatus.messages[state]!), findsOneWidget);
      expect(find.textContaining(id), findsNothing);
      expect(find.text('取消申請'), findsNothing);
      expect(reader.calls, 1);
    }
  });
  testWidgets('offline does not read; online manual retry only',
      (tester) async {
    final reader = Reader()..online = false;
    await tester.pumpWidget(page(reader));
    await tester.pumpAndSettle();
    expect(reader.calls, 0);
    expect(find.textContaining('目前離線'), findsOneWidget);
    reader.online = true;
    reader.changed();
    await tester.pump();
    expect(reader.calls, 0);
    await tester.tap(find.text('重新查詢'));
    await tester.pumpAndSettle();
    expect(reader.calls, 1);
  });
  testWidgets('error is fixed and recheck is explicit', (tester) async {
    final reader = Reader()
      ..response = (() async => throw StateError('private-secret-sentinel'));
    await tester.pumpWidget(page(reader));
    await tester.pumpAndSettle();
    expect(find.textContaining('private-secret-sentinel'), findsNothing);
    expect(find.textContaining('目前無法確認'), findsOneWidget);
    reader.response = () async => envelope('processing');
    await tester.tap(find.text('重新查詢'));
    await tester.pumpAndSettle();
    expect(reader.calls, 2);
    expect(find.text(AccountErasureStatus.messages['processing']!),
        findsOneWidget);
  });
  testWidgets('replaced reader ignores late old response', (tester) async {
    final delayed = Completer<Map<String, dynamic>>();
    final old = Reader()..response = (() => delayed.future);
    await tester.pumpWidget(page(old));
    await tester.pump();
    final fresh = Reader()..response = (() async => envelope('processing'));
    await tester.pumpWidget(page(fresh));
    await tester.pumpAndSettle();
    delayed.complete(envelope('completed'));
    await tester.pumpAndSettle();
    expect(find.text(AccountErasureStatus.messages['processing']!),
        findsOneWidget);
    expect(
        find.text(AccountErasureStatus.messages['completed']!), findsNothing);
  });
  testWidgets('invalidation clears status and discards outstanding response',
      (tester) async {
    final delayed = Completer<Map<String, dynamic>>();
    final reader = Reader()..response = (() => delayed.future);
    await tester.pumpWidget(page(reader));
    await tester.pump();
    reader.current = false;
    reader.changed();
    await tester.pump();
    delayed.complete(envelope('completed'));
    await tester.pumpAndSettle();
    expect(find.textContaining('查詢憑證已變更'), findsOneWidget);
    expect(
        find.text(AccountErasureStatus.messages['completed']!), findsNothing);
  });
  testWidgets('wrong job and offline after response are not displayed',
      (tester) async {
    final reader = Reader()
      ..response = (() async =>
          {...envelope(), 'id': '22222222-2222-4222-8222-222222222222'});
    await tester.pumpWidget(page(reader));
    await tester.pumpAndSettle();
    expect(find.textContaining('目前無法確認'), findsOneWidget);
    reader.response = () async {
      reader.online = false;
      return envelope('completed');
    };
    await tester.tap(find.text('重新查詢'));
    await tester.pumpAndSettle();
    expect(find.textContaining('目前離線'), findsOneWidget);
  });
}
