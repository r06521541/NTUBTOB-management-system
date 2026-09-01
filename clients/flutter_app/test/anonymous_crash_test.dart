import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/anonymous_crash.dart';
import 'package:ntubtob_portal/foundation.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/local_preferences.dart';

class _MutableClock {
  _MutableClock(this.value);
  DateTime value;
  DateTime call() => value;
}

class _QueueWriteFailingStore extends MemoryStore {
  @override
  Future<void> write(String key, String value) async {
    if (key.endsWith(':queue')) throw StateError('private diagnostic sentinel');
    await super.write(key, value);
  }
}

class _ScriptedSink implements AnonymousCrashSink {
  _ScriptedSink(this.results);
  final List<CrashDeliveryDisposition> results;
  final List<AnonymousCrashEvent> received = [];

  @override
  Future<CrashDeliveryDisposition> submit(AnonymousCrashEvent event) async {
    received.add(event);
    return results.removeAt(0);
  }
}

class _NeverSink implements AnonymousCrashSink {
  @override
  Future<CrashDeliveryDisposition> submit(AnonymousCrashEvent event) =>
      Completer<CrashDeliveryDisposition>().future;
}

class _PermissionPort implements NotificationPermissionPort {
  @override
  Future<void> openSystemSettings() async {}

  @override
  Future<bool> requestPermission() async => false;
}

class _ThrowingStackTrace implements StackTrace {
  @override
  String toString() => throw StateError('private stack conversion failed');
}

AnonymousCrashEvent event({
  AnonymousCrashSource source = AnonymousCrashSource.zone,
  Object error = const FormatException('private-token-sentinel'),
  StackTrace? stackTrace,
  DateTime? now,
}) =>
    AnonymousCrashEvent.capture(
      source: source,
      error: error,
      stackTrace: stackTrace ??
          StackTrace.fromString(
            '#0 secretUser package:ntubtob_portal/basic_app.dart:10:20\n'
            '#1 https://private.invalid/token external.dart:4:2',
          ),
      now: now ?? DateTime.utc(2026, 9, 1, 12, 34),
      appFlavor: AppFlavor.staging,
      platformClass: 'android',
    );

void main() {
  group('anonymous event', () {
    test('uses fixed deidentified schema without raw error or stack material',
        () {
      final captured = event();
      final encoded = jsonEncode(captured.toJson());

      expect(captured.category, AnonymousCrashCategory.format);
      expect(captured.dayUtc, DateTime.utc(2026, 9, 1));
      expect(captured.fingerprint, matches(RegExp(r'^[0-9a-f]{16}$')));
      for (final prohibited in [
        'private-token-sentinel',
        'secretUser',
        'private.invalid',
        'basic_app.dart',
        ':10:20',
      ]) {
        expect(encoded, isNot(contains(prohibited)));
      }
      expect(
        AnonymousCrashEvent.fromJson(captured.toJson()).toJson(),
        captured.toJson(),
      );
    });

    test('fingerprint is stable across line numbers and ignores third party',
        () {
      final first = event(
        stackTrace: StackTrace.fromString(
          '#0 a package:ntubtob_portal/integration.dart:1:2\n'
          '#1 private https://secret.invalid/x',
        ),
      );
      final second = event(
        stackTrace: StackTrace.fromString(
          '#0 another package:ntubtob_portal/integration.dart:999:88\n'
          '#1 other package:third_party/private.dart:2:4',
        ),
      );
      expect(first.fingerprint, second.fingerprint);
      expect(
        event(stackTrace: StackTrace.fromString('private external frame only'))
            .fingerprint,
        'none',
      );
    });

    test('unknown platform and error are bounded categories', () {
      final captured = AnonymousCrashEvent.capture(
        source: AnonymousCrashSource.platformDispatcher,
        error: Object(),
        stackTrace: StackTrace.empty,
        now: DateTime.utc(2026, 9, 1),
        appFlavor: AppFlavor.production,
        platformClass: 'private-device-model',
      );
      expect(captured.category, AnonymousCrashCategory.unknown);
      expect(captured.platformClass, 'other');
    });
  });

  group('bounded queue', () {
    test('is default-off and opt-out purges retained events', () async {
      final store = MemoryStore();
      final queue = AnonymousCrashQueue(store, 'installation');
      expect(await queue.capture(event()), isFalse);
      expect(await queue.pending(), isEmpty);

      await queue.optIn();
      expect(await queue.capture(event()), isTrue);
      expect(await queue.pending(), hasLength(1));
      await queue.optOut();
      expect(await queue.enabled(), isFalse);
      expect(await queue.pending(), isEmpty);
      expect(await queue.capture(event()), isFalse);
    });

    test('serializes concurrent capture and keeps only newest bounded events',
        () async {
      final store = MemoryStore();
      final queue = AnonymousCrashQueue(store, 'installation');
      await queue.optIn();
      final results = await Future.wait([
        for (var index = 0; index < 20; index++)
          queue.capture(event(
            source: AnonymousCrashSource
                .values[index % AnonymousCrashSource.values.length],
          )),
      ]);
      expect(results, everyElement(isTrue));
      expect(await queue.pending(), hasLength(crashQueueMaximumEvents));
      final serialized = store.values.values.join('\n');
      expect(utf8.encode(serialized).length, lessThan(crashQueueMaximumBytes));
    });

    test('expires old events and clears corrupt, oversized, and future queues',
        () async {
      final store = MemoryStore();
      final clock = _MutableClock(DateTime.utc(2026, 9, 10));
      final queue = AnonymousCrashQueue(
        store,
        'installation',
        clock: clock.call,
      );
      await queue.optIn();
      expect(
        await queue.capture(event(now: DateTime.utc(2026, 9, 1))),
        isTrue,
      );
      expect(await queue.pending(), isEmpty);
      expect(
        store.values,
        isNot(contains('anonymous-crash:v1:installation:queue')),
      );

      const key = 'anonymous-crash:v1:installation:queue';
      for (final invalid in [
        '{private-token-sentinel',
        jsonEncode({'version': 99, 'events': []}),
        'x' * (crashQueueMaximumBytes + 1),
      ]) {
        await store.write(key, invalid);
        expect(await queue.pending(), isEmpty);
        expect(store.values, isNot(contains(key)));
      }
    });

    test('capture failures are swallowed and never expose private reason',
        () async {
      final store = _QueueWriteFailingStore();
      final queue = AnonymousCrashQueue(store, 'installation');
      await queue.optIn();
      expect(await queue.capture(event()), isFalse);
      expect(await queue.pending(), isEmpty);
    });

    test('sink is explicit; retry retains while accepted and terminal remove',
        () async {
      final queue = AnonymousCrashQueue(MemoryStore(), 'installation');
      await queue.optIn();
      await queue.capture(event(source: AnonymousCrashSource.zone));
      await queue.capture(event(source: AnonymousCrashSource.flutterFramework));
      expect(await queue.flush(null), 0);
      expect(await queue.pending(), hasLength(2));

      final retry = _ScriptedSink([CrashDeliveryDisposition.retryLater]);
      expect(await queue.flush(retry), 0);
      expect(await queue.pending(), hasLength(2));

      final finish = _ScriptedSink([
        CrashDeliveryDisposition.accepted,
        CrashDeliveryDisposition.terminalReject,
      ]);
      expect(await queue.flush(finish), 2);
      expect(await queue.pending(), isEmpty);
    });

    test('sink timeout is bounded and retains pending event', () async {
      final queue = AnonymousCrashQueue(
        MemoryStore(),
        'installation',
        deliveryTimeout: const Duration(milliseconds: 1),
      );
      await queue.optIn();
      await queue.capture(event());
      expect(await queue.flush(_NeverSink()), 0);
      expect(await queue.pending(), hasLength(1));
    });
  });

  test('capture hooks preserve existing handler results and ordering',
      () async {
    final queue = AnonymousCrashQueue(MemoryStore(), 'installation');
    await queue.optIn();
    final hooks = AnonymousCrashHooks(AnonymousCrashReporter(
      queue: queue,
      appFlavor: AppFlavor.staging,
      platformClass: 'ios',
    ));
    var flutterCalls = 0;
    hooks.flutter(
      FlutterErrorDetails(
        exception: StateError('private'),
        stack:
            StackTrace.fromString('#0 a package:ntubtob_portal/main.dart:1:1'),
      ),
      (_) => flutterCalls++,
    );
    var platformCalls = 0;
    expect(
      hooks.platform(
        RangeError('private'),
        StackTrace.empty,
        (_, __) {
          platformCalls++;
          return true;
        },
      ),
      isTrue,
    );
    var zoneCalls = 0;
    hooks.zone(TypeError(), StackTrace.empty, (_, __) => zoneCalls++);
    expect([flutterCalls, platformCalls, zoneCalls], [1, 1, 1]);
    expect(await queue.pending(), hasLength(3));
    expect(
      await AnonymousCrashReporter(
        queue: queue,
        appFlavor: AppFlavor.staging,
        platformClass: 'android',
      ).capture(
        AnonymousCrashSource.zone,
        StateError('private'),
        _ThrowingStackTrace(),
      ),
      isFalse,
    );
  });

  testWidgets('preference requires notice confirmation and opt-out purges',
      (tester) async {
    final store = MemoryStore();
    final queue = AnonymousCrashQueue(store, 'installation');
    await tester.pumpWidget(MaterialApp(
      home: LocalPreferencesPage(
        preferences: LocalPreferences(store, 'installation'),
        crashQueue: queue,
        permissions: NotificationPermissionActions(_PermissionPort()),
        onThemeChanged: (_) {},
      ),
    ));
    await tester.pump();

    await tester.drag(find.byType(ListView), const Offset(0, -300));
    await tester.pumpAndSettle();
    await tester.tap(
        find.byKey(const ValueKey('anonymous-crash-reporting-preference')));
    await tester.pumpAndSettle();
    expect(find.text('啟用匿名錯誤診斷？'), findsOneWidget);
    expect(find.textContaining('不保存帳號'), findsOneWidget);
    await tester.tap(find.text('同意啟用'));
    await tester.pumpAndSettle();
    expect(await queue.enabled(), isTrue);

    await queue.capture(event());
    await tester.tap(
        find.byKey(const ValueKey('anonymous-crash-reporting-preference')));
    await tester.pumpAndSettle();
    expect(await queue.enabled(), isFalse);
    expect(await queue.pending(), isEmpty);
  });
}
