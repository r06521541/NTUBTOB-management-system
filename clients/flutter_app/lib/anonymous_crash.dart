import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'foundation.dart';
import 'integration.dart';

const crashEventVersion = 1;
const crashQueueVersion = 1;
const crashQueueMaximumEvents = 8;
const crashQueueMaximumBytes = 8192;
const crashEventMaximumBytes = 512;
const crashQueueRetention = Duration(days: 7);
const crashDeliveryTimeout = Duration(seconds: 5);

enum AnonymousCrashSource { flutterFramework, platformDispatcher, zone }

enum AnonymousCrashCategory {
  assertion,
  state,
  range,
  type,
  format,
  timeout,
  platform,
  network,
  unknown,
}

enum CrashDeliveryDisposition { accepted, retryLater, terminalReject }

class AnonymousCrashEvent {
  const AnonymousCrashEvent({
    required this.source,
    required this.category,
    required this.dayUtc,
    required this.appFlavor,
    required this.platformClass,
    required this.fingerprint,
  });

  factory AnonymousCrashEvent.capture({
    required AnonymousCrashSource source,
    required Object error,
    required StackTrace stackTrace,
    required DateTime now,
    required AppFlavor appFlavor,
    required String platformClass,
  }) {
    final utc = now.toUtc();
    return AnonymousCrashEvent(
      source: source,
      category: _categoryFor(error),
      dayUtc: DateTime.utc(utc.year, utc.month, utc.day),
      appFlavor: appFlavor,
      platformClass: _platformClass(platformClass),
      fingerprint: _firstPartyFingerprint(stackTrace),
    );
  }

  factory AnonymousCrashEvent.fromJson(Map<String, dynamic> json) {
    const keys = {
      'version',
      'source',
      'category',
      'day_utc',
      'app_flavor',
      'platform_class',
      'fingerprint',
    };
    if (json.keys.toSet().difference(keys).isNotEmpty ||
        keys.difference(json.keys.toSet()).isNotEmpty ||
        json['version'] != crashEventVersion) {
      throw const FormatException('invalid anonymous crash event');
    }
    final day = DateTime.tryParse(json['day_utc'] as String? ?? '');
    final fingerprint = json['fingerprint'];
    if (day == null ||
        !day.isUtc ||
        day.hour != 0 ||
        day.minute != 0 ||
        day.second != 0 ||
        fingerprint is! String ||
        !RegExp(r'^(?:none|[0-9a-f]{16})$').hasMatch(fingerprint)) {
      throw const FormatException('invalid anonymous crash event');
    }
    return AnonymousCrashEvent(
      source: AnonymousCrashSource.values.byName(json['source'] as String),
      category:
          AnonymousCrashCategory.values.byName(json['category'] as String),
      dayUtc: day,
      appFlavor: AppFlavor.values.byName(json['app_flavor'] as String),
      platformClass: _platformClass(json['platform_class'] as String),
      fingerprint: fingerprint,
    );
  }

  final AnonymousCrashSource source;
  final AnonymousCrashCategory category;
  final DateTime dayUtc;
  final AppFlavor appFlavor;
  final String platformClass;
  final String fingerprint;

  Map<String, dynamic> toJson() => {
        'version': crashEventVersion,
        'source': source.name,
        'category': category.name,
        'day_utc': dayUtc.toUtc().toIso8601String(),
        'app_flavor': appFlavor.name,
        'platform_class': platformClass,
        'fingerprint': fingerprint,
      };
}

abstract interface class AnonymousCrashSink {
  Future<CrashDeliveryDisposition> submit(AnonymousCrashEvent event);
}

class AnonymousCrashQueue {
  AnonymousCrashQueue(
    this.store,
    this.installationId, {
    DateTime Function()? clock,
    this.deliveryTimeout = crashDeliveryTimeout,
  }) : clock = clock ?? DateTime.now;

  final DurableStore store;
  final String installationId;
  final DateTime Function() clock;
  final Duration deliveryTimeout;
  Future<void> _tail = Future<void>.value();

  String get _queueKey => 'anonymous-crash:v1:$installationId:queue';
  String get _consentKey => 'anonymous-crash:v1:$installationId:consent';

  Future<bool> enabled() async {
    try {
      return await store.read(_consentKey) == 'enabled';
    } on Object {
      return false;
    }
  }

  Future<void> optIn() => _serialized(() async {
        await store.delete(_queueKey);
        await store.write(_consentKey, 'enabled');
      });

  Future<void> optOut() => _serialized(() async {
        await store.write(_consentKey, 'disabled');
        await store.delete(_queueKey);
      });

  Future<bool> capture(AnonymousCrashEvent event) async {
    try {
      return await _serialized(() async {
        if (await store.read(_consentKey) != 'enabled') return false;
        final events = await _readValidEvents();
        events.add(event);
        final bounded = _bounded(events, clock().toUtc());
        if (bounded.isEmpty) {
          await store.delete(_queueKey);
          return true;
        }
        final encoded = _encodeQueue(bounded);
        if (utf8.encode(encoded).length > crashQueueMaximumBytes) return false;
        await store.write(_queueKey, encoded);
        return true;
      });
    } on Object {
      return false;
    }
  }

  Future<List<AnonymousCrashEvent>> pending() async {
    try {
      return await _serialized(() async =>
          List<AnonymousCrashEvent>.unmodifiable(await _readValidEvents()));
    } on Object {
      return const [];
    }
  }

  Future<int> flush(AnonymousCrashSink? sink) async {
    if (sink == null) return 0;
    try {
      return await _serialized(() async {
        if (await store.read(_consentKey) != 'enabled') return 0;
        final pending = await _readValidEvents();
        var removed = 0;
        while (pending.isNotEmpty) {
          final disposition =
              await sink.submit(pending.first).timeout(deliveryTimeout);
          if (disposition == CrashDeliveryDisposition.retryLater) break;
          pending.removeAt(0);
          removed++;
        }
        if (pending.isEmpty) {
          await store.delete(_queueKey);
        } else {
          await store.write(_queueKey, _encodeQueue(pending));
        }
        return removed;
      });
    } on Object {
      return 0;
    }
  }

  Future<List<AnonymousCrashEvent>> _readValidEvents() async {
    final raw = await store.read(_queueKey);
    if (raw == null) return [];
    if (utf8.encode(raw).length > crashQueueMaximumBytes) {
      await store.delete(_queueKey);
      return [];
    }
    try {
      final document = jsonDecode(raw) as Map<String, dynamic>;
      if (document.keys.toSet().difference({'version', 'events'}).isNotEmpty ||
          document.keys.length != 2 ||
          document['version'] != crashQueueVersion ||
          document['events'] is! List<dynamic>) {
        throw const FormatException('invalid anonymous crash queue');
      }
      final events = (document['events'] as List<dynamic>)
          .map((value) => AnonymousCrashEvent.fromJson(
                (value as Map).cast<String, dynamic>(),
              ))
          .toList(growable: true);
      if (events.length > crashQueueMaximumEvents ||
          events.any((event) =>
              utf8.encode(jsonEncode(event.toJson())).length >
              crashEventMaximumBytes)) {
        throw const FormatException('invalid anonymous crash queue');
      }
      final bounded = _bounded(events, clock().toUtc());
      if (bounded.length != events.length) {
        if (bounded.isEmpty) {
          await store.delete(_queueKey);
        } else {
          await store.write(_queueKey, _encodeQueue(bounded));
        }
      }
      return bounded;
    } on Object {
      await store.delete(_queueKey);
      return [];
    }
  }

  List<AnonymousCrashEvent> _bounded(
    List<AnonymousCrashEvent> events,
    DateTime now,
  ) {
    final oldest = DateTime.utc(now.year, now.month, now.day)
        .subtract(crashQueueRetention);
    final retained = events
        .where((event) => !event.dayUtc.isBefore(oldest))
        .toList(growable: true);
    if (retained.length > crashQueueMaximumEvents) {
      retained.removeRange(0, retained.length - crashQueueMaximumEvents);
    }
    return retained;
  }

  String _encodeQueue(List<AnonymousCrashEvent> events) => jsonEncode({
        'version': crashQueueVersion,
        'events': events.map((event) => event.toJson()).toList(growable: false),
      });

  Future<T> _serialized<T>(Future<T> Function() action) {
    final completer = Completer<T>();
    _tail = _tail.catchError((Object _) {}).then((_) async {
      try {
        completer.complete(await action());
      } on Object catch (error, stackTrace) {
        completer.completeError(error, stackTrace);
      }
    });
    return completer.future;
  }
}

class AnonymousCrashReporter {
  const AnonymousCrashReporter({
    required this.queue,
    required this.appFlavor,
    required this.platformClass,
  });

  final AnonymousCrashQueue queue;
  final AppFlavor appFlavor;
  final String platformClass;

  Future<bool> capture(
    AnonymousCrashSource source,
    Object error,
    StackTrace stackTrace,
  ) async {
    try {
      return await queue.capture(AnonymousCrashEvent.capture(
        source: source,
        error: error,
        stackTrace: stackTrace,
        now: queue.clock(),
        appFlavor: appFlavor,
        platformClass: platformClass,
      ));
    } on Object {
      return false;
    }
  }
}

class AnonymousCrashHooks {
  const AnonymousCrashHooks(this.reporter);
  final AnonymousCrashReporter reporter;

  void flutter(
    FlutterErrorDetails details,
    FlutterExceptionHandler? previous,
  ) {
    unawaited(reporter.capture(
      AnonymousCrashSource.flutterFramework,
      details.exception,
      details.stack ?? StackTrace.empty,
    ));
    (previous ?? FlutterError.presentError)(details);
  }

  bool platform(
    Object error,
    StackTrace stackTrace,
    bool Function(Object, StackTrace)? previous,
  ) {
    unawaited(reporter.capture(
      AnonymousCrashSource.platformDispatcher,
      error,
      stackTrace,
    ));
    return previous?.call(error, stackTrace) ?? false;
  }

  void zone(
    Object error,
    StackTrace stackTrace,
    void Function(Object, StackTrace) previous,
  ) {
    unawaited(reporter.capture(AnonymousCrashSource.zone, error, stackTrace));
    previous(error, stackTrace);
  }
}

AnonymousCrashCategory _categoryFor(Object error) => switch (error) {
      AssertionError() => AnonymousCrashCategory.assertion,
      StateError() => AnonymousCrashCategory.state,
      RangeError() => AnonymousCrashCategory.range,
      TypeError() => AnonymousCrashCategory.type,
      FormatException() => AnonymousCrashCategory.format,
      TimeoutException() => AnonymousCrashCategory.timeout,
      PlatformException() => AnonymousCrashCategory.platform,
      NetworkException() => AnonymousCrashCategory.network,
      _ => AnonymousCrashCategory.unknown,
    };

String _platformClass(String value) => switch (value) {
      'android' || 'ios' => value,
      _ => 'other',
    };

String _firstPartyFingerprint(StackTrace stackTrace) {
  final frames = <String>[];
  final pattern = RegExp(r'package:ntubtob_portal/([A-Za-z0-9_./-]+\.dart)');
  for (final line in stackTrace.toString().split('\n')) {
    final match = pattern.firstMatch(line);
    if (match == null) continue;
    frames.add(match.group(1)!);
    if (frames.length == 8) break;
  }
  if (frames.isEmpty) return 'none';
  var hash = BigInt.parse('cbf29ce484222325', radix: 16);
  final prime = BigInt.parse('100000001b3', radix: 16);
  final mask = BigInt.parse('ffffffffffffffff', radix: 16);
  for (final byte in utf8.encode(frames.join('\n'))) {
    hash ^= BigInt.from(byte);
    hash = (hash * prime) & mask;
  }
  return hash.toRadixString(16).padLeft(16, '0');
}
