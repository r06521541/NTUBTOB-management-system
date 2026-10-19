import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_flow.dart';
import 'package:ntubtob_portal/account_erasure_status.dart';

const job = '11111111-1111-4111-8111-111111111111';
const otherJob = '22222222-2222-4222-8222-222222222222';
const privateSentinel = 'fictional-private-receipt-secret';

Map<String, dynamic> status([String value = 'requested']) => {
      'id': job,
      'status': value,
      'requested_at': '2035-01-01T00:00:00Z',
      'updated_at': '2035-01-01T00:00:01Z',
    };

class FlowPort extends ChangeNotifier implements AccountErasureFlowPort {
  bool get observed => hasListeners;

  @override
  Listenable get changes => this;
  @override
  bool online = true;
  @override
  int generation = 0;
  @override
  bool canRequest = true;
  @override
  bool outcomeUnknown = false;
  @override
  String? jobId;
  bool current = true;
  int reads = 0;
  final calls = <String>[];
  Future<Map<String, dynamic>?> Function()? readResponse;
  Future<void> Function(String)? actionResponse;

  @override
  void requireCurrent() {
    if (!current) throw StateError(privateSentinel);
  }

  @override
  Future<Map<String, dynamic>?> readStatus() {
    reads++;
    return readResponse?.call() ??
        Future.value(jobId == null ? null : status());
  }

  Future<void> _act(String name, bool confirmed) async {
    expect(confirmed, isTrue);
    calls.add(name);
    if (actionResponse != null) {
      await actionResponse!(name);
    } else if (name == 'request' || name == 'recover') {
      jobId = job;
    }
  }

  @override
  Future<void> request({required bool confirmed}) => _act('request', confirmed);
  @override
  Future<void> verify({required bool confirmed}) => _act('verify', confirmed);
  @override
  Future<void> cancel({required bool confirmed}) => _act('cancel', confirmed);
  @override
  Future<void> recoverReceipt({required bool confirmed}) =>
      _act('recover', confirmed);

  void changed() => notifyListeners();
}

Widget page(FlowPort port) =>
    MaterialApp(home: AccountErasureFlowPage(port: port));
Finder action(String name) => find.byKey(ValueKey('erasure-flow-$name'));
Finder confirm(String name) =>
    find.byKey(ValueKey('confirm-erasure-flow-$name'));

Future<void> submit(WidgetTester tester, String name) async {
  await tester.tap(action(name));
  await tester.pumpAndSettle();
  await tester.tap(confirm(name));
  await tester.pump();
}

void main() {
  testWidgets('request requires onsite confirmation and never claims erasure',
      (tester) async {
    final port = FlowPort();
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    expect(port.calls, isEmpty);
    await tester.tap(action('request'));
    await tester.pumpAndSettle();
    expect(port.calls, isEmpty);
    await tester.tap(find.text('返回'));
    await tester.pumpAndSettle();
    expect(port.calls, isEmpty);
    await submit(tester, 'request');
    await tester.pumpAndSettle();
    expect(port.calls, ['request']);
    expect(find.textContaining('尚未刪除'), findsWidgets);
    expect(find.textContaining(job), findsNothing);
    expect(find.textContaining(privateSentinel), findsNothing);
    await tester.tap(action('status'));
    await tester.pumpAndSettle();
    expect(
        find.text(AccountErasureStatus.messages['requested']!), findsOneWidget);
    expect(port.calls, ['request']);
  });

  testWidgets('missing receipt does not grant request authority',
      (tester) async {
    final port = FlowPort()..canRequest = false;
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    expect(action('request'), findsNothing);
    expect(port.calls, isEmpty);
    expect(action('recover'), findsOneWidget);
  });

  testWidgets('request success without a receipt remains unknown and read-only',
      (tester) async {
    final port = FlowPort()..actionResponse = ((_) async {});
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    await submit(tester, 'request');
    await tester.pumpAndSettle();
    await tester.tap(action('status'));
    await tester.pumpAndSettle();
    expect(port.jobId, isNull);
    expect(port.calls, ['request']);
    expect(action('request'), findsNothing);
    expect(action('recover'), findsNothing);
    expect(find.textContaining('送出結果尚未確認'), findsOneWidget);
  });

  testWidgets('recovery is explicit receipt reopening and never a new request',
      (tester) async {
    final port = FlowPort()..canRequest = false;
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    await submit(tester, 'recover');
    await tester.pumpAndSettle();
    expect(port.calls, ['recover']);
    await tester.tap(action('status'));
    await tester.pumpAndSettle();
    expect(
        find.text(AccountErasureStatus.messages['requested']!), findsOneWidget);
    expect(port.calls, ['recover']);
  });

  testWidgets('verification and cancellation are separate confirmed actions',
      (tester) async {
    for (final name in ['verify', 'cancel']) {
      final port = FlowPort()..jobId = job;
      await tester.pumpWidget(page(port));
      await tester.pumpAndSettle();
      await tester.tap(action(name));
      await tester.pumpAndSettle();
      expect(port.calls, isEmpty);
      await tester.tap(confirm(name));
      await tester.pumpAndSettle();
      expect(port.calls, [name]);
      expect(find.textContaining(job), findsNothing);
    }
  });

  testWidgets('all server statuses remain truthful and terminal cannot mutate',
      (tester) async {
    for (final value in AccountErasureStatus.messages.keys) {
      final port = FlowPort()
        ..jobId = job
        ..readResponse = (() async => status(value));
      await tester.pumpWidget(page(port));
      await tester.pumpAndSettle();
      expect(find.text(AccountErasureStatus.messages[value]!), findsOneWidget);
      expect(action('request'), findsNothing);
      if (['online_completed', 'completed', 'cancelled'].contains(value)) {
        expect(action('verify'), findsNothing);
        expect(action('cancel'), findsNothing);
      }
      expect(port.calls, isEmpty);
    }
  });

  testWidgets('changed job without notification cannot use old displayed state',
      (tester) async {
    for (final name in ['verify', 'cancel']) {
      final port = FlowPort()..jobId = job;
      await tester.pumpWidget(page(port));
      await tester.pumpAndSettle();
      port.jobId = otherJob;
      await tester.tap(action(name));
      await tester.pumpAndSettle();
      expect(confirm(name), findsNothing);
      expect(port.calls, isEmpty);
    }
  });

  testWidgets('offline makes zero reads or actions; reconnect is manual',
      (tester) async {
    final port = FlowPort()..online = false;
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    expect(port.reads, 0);
    expect(tester.widget<TextButton>(action('status')).onPressed, isNull);
    expect(port.calls, isEmpty);
    port.online = true;
    port.changed();
    await tester.pump();
    expect(port.reads, 0);
    await tester.tap(action('status'));
    await tester.pumpAndSettle();
    expect(port.reads, 1);
    expect(port.calls, isEmpty);
  });

  testWidgets(
      'unknown stays read-only through failed empty and requested reads',
      (tester) async {
    final port = FlowPort()
      ..actionResponse = ((_) async => throw StateError(privateSentinel));
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    await submit(tester, 'request');
    await tester.pumpAndSettle();
    final responses = <Future<Map<String, dynamic>?> Function()>[
      () async => throw StateError(privateSentinel),
      () async => null,
      () async => status(),
    ];
    for (var index = 0; index < responses.length; index++) {
      if (index == 2) port.jobId = job;
      port.readResponse = responses[index];
      await tester.tap(action('status'));
      await tester.pumpAndSettle();
      for (final name in ['request', 'verify', 'cancel', 'recover']) {
        expect(action(name), findsNothing);
      }
      expect(port.calls, ['request']);
      expect(find.textContaining(privateSentinel), findsNothing);
      if (index == 2) {
        expect(find.text(AccountErasureStatus.messages['requested']!),
            findsOneWidget);
      }
    }
  });

  testWidgets('injected unknown survives rebuilding the page', (tester) async {
    final port = FlowPort()
      ..jobId = job
      ..outcomeUnknown = true;
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    expect(action('verify'), findsNothing);
    expect(action('cancel'), findsNothing);
    expect(port.calls, isEmpty);
  });

  testWidgets('generation change while confirming prevents submission',
      (tester) async {
    final port = FlowPort();
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    await tester.tap(action('request'));
    await tester.pumpAndSettle();
    port.generation++;
    port.changed();
    await tester.pump();
    await tester.tap(confirm('request'));
    await tester.pumpAndSettle();
    expect(port.calls, isEmpty);
    expect(find.textContaining('查詢身分已變更'), findsOneWidget);
  });

  testWidgets('offline during confirmation prevents submission',
      (tester) async {
    final port = FlowPort();
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    await tester.tap(action('request'));
    await tester.pumpAndSettle();
    port.online = false;
    await tester.tap(confirm('request'));
    await tester.pumpAndSettle();
    expect(port.calls, isEmpty);
    expect(find.textContaining('離線'), findsWidgets);
  });

  testWidgets('busy action is single-flight; context change drops late success',
      (tester) async {
    final pending = Completer<void>();
    final port = FlowPort()..actionResponse = ((_) => pending.future);
    await tester.pumpWidget(page(port));
    await tester.pumpAndSettle();
    await submit(tester, 'request');
    expect(port.calls, ['request']);
    expect(action('request'), findsNothing);
    port.generation++;
    port.changed();
    await tester.pump();
    pending.complete();
    await tester.pumpAndSettle();
    expect(find.textContaining('查詢身分已變更'), findsOneWidget);
    expect(port.calls, ['request']);
  });

  testWidgets('replacement detaches old listener and ignores old status',
      (tester) async {
    final pending = Completer<Map<String, dynamic>?>();
    final old = FlowPort()
      ..jobId = job
      ..readResponse = (() => pending.future);
    await tester.pumpWidget(page(old));
    await tester.pump();
    final fresh = FlowPort()
      ..jobId = job
      ..readResponse = (() async => status('processing'));
    await tester.pumpWidget(page(fresh));
    await tester.pumpAndSettle();
    expect(old.observed, isFalse);
    old.changed();
    pending.complete(status('completed'));
    await tester.pumpAndSettle();
    expect(find.text(AccountErasureStatus.messages['processing']!),
        findsOneWidget);
    expect(
        find.text(AccountErasureStatus.messages['completed']!), findsNothing);
    await tester.pumpWidget(const SizedBox());
    expect(fresh.observed, isFalse);
  });

  testWidgets('malformed or cross-job status never authorizes an action',
      (tester) async {
    for (final envelope in [
      {...status(), 'id': otherJob},
      {'extra': true}
    ]) {
      final port = FlowPort()
        ..jobId = job
        ..readResponse = (() async => envelope);
      await tester.pumpWidget(page(port));
      await tester.pumpAndSettle();
      expect(action('verify'), findsNothing);
      expect(action('cancel'), findsNothing);
      expect(find.textContaining('無法確認'), findsOneWidget);
      expect(find.textContaining(otherJob), findsNothing);
    }
  });
}
