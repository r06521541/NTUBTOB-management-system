import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_line_sdk/flutter_line_sdk.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'foundation.dart';

enum ClientMode { fake, real }

class AppConfig {
  const AppConfig._(
      this.flavor, this.mode, this.apiBaseUrl, this.lineChannelId);
  final AppFlavor flavor;
  final ClientMode mode;
  final Uri? apiBaseUrl;
  final String? lineChannelId;

  static AppConfig parse(
      {required String flavor,
      required String mode,
      String apiBaseUrl = '',
      String lineChannelId = ''}) {
    final parsedFlavor = FlavorConfig.parse(flavor).flavor;
    if (parsedFlavor == AppFlavor.development) {
      if (mode != 'fake' || apiBaseUrl.isNotEmpty || lineChannelId.isNotEmpty) {
        throw const FormatException(
            'development requires an explicit isolated fake mode');
      }
      return AppConfig._(parsedFlavor, ClientMode.fake, null, null);
    }
    final uri = Uri.tryParse(apiBaseUrl);
    final validUri = uri != null &&
        uri.scheme == 'https' &&
        uri.host.isNotEmpty &&
        !uri.hasQuery &&
        !uri.hasFragment &&
        uri.userInfo.isEmpty;
    final validChannel = RegExp(r'^\d+$').hasMatch(lineChannelId);
    if (mode != 'real' || !validUri || !validChannel) {
      throw const FormatException('real configuration is missing or invalid');
    }
    return AppConfig._(parsedFlavor, ClientMode.real, uri, lineChannelId);
  }

  static AppConfig fromEnvironment() => parse(
        flavor: const String.fromEnvironment('APP_FLAVOR'),
        mode: const String.fromEnvironment('CLIENT_MODE'),
        apiBaseUrl: const String.fromEnvironment('API_BASE_URL'),
        lineChannelId: const String.fromEnvironment('LINE_CHANNEL_ID'),
      );
}

class ContractException implements Exception {
  const ContractException(this.reason);
  final String reason;
  @override
  String toString() => 'ContractException($reason)';
}

enum ApiErrorCode {
  malformedRequest,
  unauthenticated,
  sessionExpired,
  identityPending,
  accountUnavailable,
  forbidden,
  resourceNotFound,
  idempotencyConflict,
  stateConflict,
  validationFailed,
  rateLimited,
  serviceUnavailable,
  serverError
}

class ApiError implements Exception {
  const ApiError(this.code, this.retryable, this.retryAfterSeconds);
  factory ApiError.fromJson(Map<String, dynamic> envelope) {
    final error = _required<Map<String, dynamic>>(envelope, 'error');
    _required<String>(error, 'message');
    _required<String>(error, 'request_id');
    _required<List<dynamic>>(error, 'field_errors');
    return ApiError(
        switch (_required<String>(error, 'code')) {
          'malformed_request' => ApiErrorCode.malformedRequest,
          'unauthenticated' => ApiErrorCode.unauthenticated,
          'session_expired' => ApiErrorCode.sessionExpired,
          'identity_pending' => ApiErrorCode.identityPending,
          'account_unavailable' => ApiErrorCode.accountUnavailable,
          'forbidden' => ApiErrorCode.forbidden,
          'resource_not_found' => ApiErrorCode.resourceNotFound,
          'idempotency_conflict' => ApiErrorCode.idempotencyConflict,
          'state_conflict' => ApiErrorCode.stateConflict,
          'validation_failed' => ApiErrorCode.validationFailed,
          'rate_limited' => ApiErrorCode.rateLimited,
          'service_unavailable' => ApiErrorCode.serviceUnavailable,
          'server_error' => ApiErrorCode.serverError,
          _ => throw const ContractException('unknown API error code'),
        },
        _required<bool>(error, 'retryable'),
        _nullable<int>(error, 'retry_after_seconds'));
  }
  final ApiErrorCode code;
  final bool retryable;
  final int? retryAfterSeconds;
}

class NetworkException implements Exception {
  const NetworkException();
}

class AuthorizedRequestNetworkException extends NetworkException {
  const AuthorizedRequestNetworkException();
}

class SessionExpiredException implements Exception {
  const SessionExpiredException();
}

T _required<T>(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! T) throw ContractException('invalid required field: $key');
  return value;
}

T? _nullable<T>(Map<String, dynamic> json, String key) {
  if (!json.containsKey(key)) {
    throw ContractException('missing nullable field: $key');
  }
  final value = json[key];
  if (value != null && value is! T) {
    throw ContractException('invalid nullable field: $key');
  }
  return value as T?;
}

DateTime _utcDate(Map<String, dynamic> json, String key) {
  final raw = _required<String>(json, key);
  final value = DateTime.tryParse(raw);
  if (value == null || !value.isUtc || !raw.endsWith('Z')) {
    throw ContractException('invalid UTC date: $key');
  }
  return value;
}

enum AttendanceReply {
  attending,
  notAttending,
  arrivingLate,
  leavingEarly,
  undecided
}

extension AttendanceReplyWire on AttendanceReply {
  String get wire => switch (this) {
        AttendanceReply.attending => 'attending',
        AttendanceReply.notAttending => 'not_attending',
        AttendanceReply.arrivingLate => 'arriving_late',
        AttendanceReply.leavingEarly => 'leaving_early',
        AttendanceReply.undecided => 'undecided',
      };
  static AttendanceReply parse(Object? value) => switch (value) {
        'attending' => AttendanceReply.attending,
        'not_attending' => AttendanceReply.notAttending,
        'arriving_late' => AttendanceReply.arrivingLate,
        'leaving_early' => AttendanceReply.leavingEarly,
        'undecided' => AttendanceReply.undecided,
        _ => throw const ContractException('unknown attendance reply'),
      };
}

class SessionEnvelope {
  const SessionEnvelope(
      {required this.accessToken,
      required this.refreshToken,
      required this.sessionId,
      required this.expiresIn});
  factory SessionEnvelope.fromJson(Map<String, dynamic> json) {
    final expires = _required<int>(json, 'expires_in');
    if (expires != 900) {
      throw const ContractException('invalid access lifetime');
    }
    return SessionEnvelope(
        accessToken: _required(json, 'access_token'),
        refreshToken: _required(json, 'refresh_token'),
        sessionId: _required(json, 'session_id'),
        expiresIn: expires);
  }
  final String accessToken, refreshToken, sessionId;
  final int expiresIn;
}

enum AccessLevel { basic, officer, admin }

class Person {
  const Person(this.id, this.displayName, this.capabilities,
      {this.accessLevel = AccessLevel.basic});
  factory Person.fromJson(Map<String, dynamic> json) {
    final accessLevel = switch (json['access_level']) {
      'basic' => AccessLevel.basic,
      'officer' => AccessLevel.officer,
      'admin' => AccessLevel.admin,
      _ => throw const ContractException('unknown access level'),
    };
    final caps = _required<List<dynamic>>(json, 'capabilities');
    const allowed = {
      'games:read',
      'attendance:reply:self',
      'notifications:read',
      'attendance:report:read',
      'notifications:publish',
    };
    if (caps.any((e) => e is! String || !allowed.contains(e))) {
      throw const ContractException('unknown capability');
    }
    return Person(_required(json, 'id'), _required(json, 'display_name'),
        caps.cast<String>(),
        accessLevel: accessLevel);
  }
  final String id, displayName;
  final AccessLevel accessLevel;
  final List<String> capabilities;
  bool get canReadAttendanceReport =>
      accessLevel != AccessLevel.basic &&
      capabilities.contains('attendance:report:read');
  bool get canReadNotifications => capabilities.contains('notifications:read');
  bool get canPublishNotifications =>
      capabilities.contains('notifications:publish');
  Map<String, dynamic> toJson() => {
        'id': id,
        'display_name': displayName,
        'access_level': accessLevel.name,
        'capabilities': capabilities,
      };
}

class AttendanceReportPerson {
  const AttendanceReportPerson(this.personId, this.displayName, this.reply);
  factory AttendanceReportPerson.fromJson(Map<String, dynamic> json) =>
      AttendanceReportPerson(
        _required(json, 'person_id'),
        _required(json, 'display_name'),
        AttendanceReplyWire.parse(json['reply']),
      );
  final String personId, displayName;
  final AttendanceReply reply;
}

class AttendanceReportUnansweredPerson {
  const AttendanceReportUnansweredPerson({
    required this.personId,
    required this.displayName,
    required this.observedReplies,
    required this.observedGames,
    required this.responseRate,
    required this.participationRate,
    required this.nonparticipationRate,
  });
  factory AttendanceReportUnansweredPerson.fromJson(Map<String, dynamic> json) {
    final observedReplies = _required<int>(json, 'observed_replies');
    final observedGames = _required<int>(json, 'observed_games');
    final responseRate = _required<int>(json, 'response_rate');
    final participationRate = _required<int>(json, 'participation_rate');
    final nonparticipationRate = _required<int>(json, 'nonparticipation_rate');
    if (observedReplies < 1 ||
        observedGames < 1 ||
        !_percentage(responseRate) ||
        !_percentage(participationRate) ||
        !_percentage(nonparticipationRate)) {
      throw const ContractException('invalid report observation');
    }
    return AttendanceReportUnansweredPerson(
      personId: _required(json, 'person_id'),
      displayName: _required(json, 'display_name'),
      observedReplies: observedReplies,
      observedGames: observedGames,
      responseRate: responseRate,
      participationRate: participationRate,
      nonparticipationRate: nonparticipationRate,
    );
  }
  final String personId, displayName;
  final int observedReplies,
      observedGames,
      responseRate,
      participationRate,
      nonparticipationRate;
}

bool _percentage(int value) => value >= 0 && value <= 100;

class AttendanceReportObservation {
  const AttendanceReportObservation(
      this.historyGames, this.historyLimit, this.minimumResponseRate);
  factory AttendanceReportObservation.fromJson(Map<String, dynamic> json) {
    final historyGames = _required<int>(json, 'history_games');
    final historyLimit = _required<int>(json, 'history_limit');
    final minimumResponseRate = _required<int>(json, 'minimum_response_rate');
    if (historyGames < 0 ||
        !const {5, 8, 12, 20}.contains(historyLimit) ||
        !_percentage(minimumResponseRate) ||
        minimumResponseRate % 10 != 0) {
      throw const ContractException('invalid report bounds');
    }
    return AttendanceReportObservation(
        historyGames, historyLimit, minimumResponseRate);
  }
  final int historyGames, historyLimit, minimumResponseRate;
}

class AttendanceReport {
  const AttendanceReport({
    required this.gameId,
    required this.generatedAt,
    required this.observation,
    required this.attending,
    required this.notAttending,
    required this.notYetReplied,
  });
  factory AttendanceReport.fromJson(Map<String, dynamic> json) =>
      AttendanceReport(
        gameId: _required(json, 'game_id'),
        generatedAt: _utcDate(json, 'generated_at'),
        observation: AttendanceReportObservation.fromJson(
            _required<Map<String, dynamic>>(json, 'observation')),
        attending: _reportPeople(json, 'attending'),
        notAttending: _reportPeople(json, 'not_attending'),
        notYetReplied: _required<List<dynamic>>(json, 'not_yet_replied')
            .map((item) => AttendanceReportUnansweredPerson.fromJson(
                item as Map<String, dynamic>))
            .toList(growable: false),
      );
  final String gameId;
  final DateTime generatedAt;
  final AttendanceReportObservation observation;
  final List<AttendanceReportPerson> attending, notAttending;
  final List<AttendanceReportUnansweredPerson> notYetReplied;
}

List<AttendanceReportPerson> _reportPeople(
        Map<String, dynamic> json, String key) =>
    _required<List<dynamic>>(json, key)
        .map((item) =>
            AttendanceReportPerson.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);

class Game {
  const Game(this.id, this.startAt, this.durationMinutes, this.location,
      this.homeTeam, this.awayTeam);
  factory Game.fromJson(Map<String, dynamic> json) => Game(
      _required(json, 'id'),
      _utcDate(json, 'start_at'),
      _nullable(json, 'duration_minutes'),
      _nullable(json, 'location'),
      _nullable(json, 'home_team'),
      _nullable(json, 'away_team'));
  final String id;
  final DateTime startAt;
  final int? durationMinutes;
  final String? location, homeTeam, awayTeam;
  Map<String, dynamic> toJson() => {
        'id': id,
        'start_at': startAt.toIso8601String(),
        'duration_minutes': durationMinutes,
        'location': location,
        'home_team': homeTeam,
        'away_team': awayTeam,
      };
}

class GamePage {
  const GamePage(this.items, this.nextCursor);
  factory GamePage.fromJson(Map<String, dynamic> json) => GamePage(
      _required<List<dynamic>>(json, 'items')
          .map((item) => Game.fromJson(item as Map<String, dynamic>))
          .toList(growable: false),
      _nullable<String>(json, 'next_cursor'));
  final List<Game> items;
  final String? nextCursor;
}

class CachedBasicData {
  const CachedBasicData(this.person, this.games, this.lastSyncedAt);
  final Person person;
  final List<Game> games;
  final DateTime lastSyncedAt;
}

class BasicCache {
  const BasicCache(this.store, this.installationId);
  final DurableStore store;
  final String installationId;
  String _key(String personId) => 'cache:v1:$installationId:$personId';
  String get _indexKey => 'cache-index:v1:$installationId';
  Future<void> save(Person person, List<Game> games, DateTime now) async {
    await store.write(
        _key(person.id),
        jsonEncode({
          'version': 1,
          'person': person.toJson(),
          'games': games.map((game) => game.toJson()).toList(),
          'last_synced_at': now.toUtc().toIso8601String(),
        }));
    await store.write(_indexKey, person.id);
  }

  Future<CachedBasicData?> load() async {
    final personId = await store.read(_indexKey);
    if (personId == null) return null;
    final raw = await store.read(_key(personId));
    if (raw == null) return null;
    try {
      final value = jsonDecode(raw) as Map<String, dynamic>;
      if (value['version'] != 1) return null;
      return CachedBasicData(
        Person.fromJson(value['person'] as Map<String, dynamic>),
        (value['games'] as List<dynamic>)
            .map((game) => Game.fromJson(game as Map<String, dynamic>))
            .toList(growable: false),
        _utcDate(value, 'last_synced_at'),
      );
    } on Object {
      return null;
    }
  }

  Future<void> clear() async {
    await store.deleteKeysWithPrefix('cache:v1:$installationId:');
    await store.delete(_indexKey);
  }

  Future<bool?> observePresence() async {
    final indexPresent = await store.containsKey(_indexKey);
    final dataCount = await store.countKeysWithPrefix(
      'cache:v1:$installationId:',
      maximum: 1,
    );
    if (!indexPresent && dataCount == 0) return false;
    if (indexPresent && dataCount == 1) return true;
    return null;
  }
}

enum MobileNotificationType {
  gameReminder,
  attendanceReminder,
  gameChange,
  officerPersonal,
  officerGameBroadcast,
  officerTeamBroadcast,
  adminSystemAnnouncement
}

const notificationRetention = Duration(days: 90);
final _maximumNotificationId = BigInt.parse('9223372036854775807');

bool _validNotificationId(String value) {
  if (value.length > 32 ||
      !RegExp(r'^notification_[1-9][0-9]*$').hasMatch(value)) {
    return false;
  }
  final parsed = BigInt.tryParse(value.substring(13));
  return parsed != null && parsed <= _maximumNotificationId;
}

extension MobileNotificationTypeWire on MobileNotificationType {
  String get wire => switch (this) {
        MobileNotificationType.gameReminder => 'game_reminder',
        MobileNotificationType.attendanceReminder => 'attendance_reminder',
        MobileNotificationType.gameChange => 'game_change',
        MobileNotificationType.officerPersonal => 'officer_personal',
        MobileNotificationType.officerGameBroadcast =>
          'officer_game_broadcast',
        MobileNotificationType.officerTeamBroadcast =>
          'officer_team_broadcast',
        MobileNotificationType.adminSystemAnnouncement =>
          'admin_system_announcement',
      };

  static MobileNotificationType parse(Object? value) => switch (value) {
        'game_reminder' => MobileNotificationType.gameReminder,
        'attendance_reminder' => MobileNotificationType.attendanceReminder,
        'game_change' => MobileNotificationType.gameChange,
        'officer_personal' => MobileNotificationType.officerPersonal,
        'officer_game_broadcast' =>
          MobileNotificationType.officerGameBroadcast,
        'officer_team_broadcast' =>
          MobileNotificationType.officerTeamBroadcast,
        'admin_system_announcement' =>
          MobileNotificationType.adminSystemAnnouncement,
        _ => throw const ContractException('unknown notification type'),
      };
}

enum NotificationDestinationType { notificationList, notification, game }

class NotificationDestination {
  const NotificationDestination._(this.type, this.id);
  const NotificationDestination.listFallback()
      : this._(NotificationDestinationType.notificationList, null);
  const NotificationDestination.notification(String id)
      : this._(NotificationDestinationType.notification, id);
  const NotificationDestination.game(String id)
      : this._(NotificationDestinationType.game, id);

  factory NotificationDestination.parseOrFallback(
      Object? value, String notificationId) {
    if (value is! Map<String, dynamic>) {
      return const NotificationDestination.listFallback();
    }
    return switch (value['type']) {
      'notification' when value['notification_id'] == notificationId =>
        NotificationDestination.notification(notificationId),
      'game'
          when value['game_id'] is String &&
              RegExp(r'^game_-?[1-9][0-9]*$')
                  .hasMatch(value['game_id'] as String) =>
        NotificationDestination.game(value['game_id'] as String),
      _ => const NotificationDestination.listFallback(),
    };
  }

  final NotificationDestinationType type;
  final String? id;

  String safeRoute({
    required bool notificationVisible,
    Set<String> authorizedGameIds = const {},
  }) {
    if (!notificationVisible) return '/notifications';
    return switch (type) {
      NotificationDestinationType.notification => '/notifications/$id',
      NotificationDestinationType.game when authorizedGameIds.contains(id) =>
        '/games/$id',
      _ => '/notifications',
    };
  }

  Map<String, dynamic> toJson() => switch (type) {
        NotificationDestinationType.notification =>
          {'type': 'notification', 'notification_id': id},
        NotificationDestinationType.game => {'type': 'game', 'game_id': id},
        NotificationDestinationType.notificationList =>
          {'type': 'notification_list'},
      };
}

class MobileNotification {
  const MobileNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    required this.createdAt,
    required this.visibleUntil,
    required this.readAt,
    this.destination = const NotificationDestination.listFallback(),
  });

  factory MobileNotification.fromJson(Map<String, dynamic> json) {
    final id = _required<String>(json, 'id');
    final title = _required<String>(json, 'title');
    final body = _required<String>(json, 'body');
    final createdAt = _utcDate(json, 'created_at');
    final visibleUntil = _utcDate(json, 'visible_until');
    final rawReadAt = _nullable<String>(json, 'read_at');
    final readAt = rawReadAt == null
        ? null
        : _utcDate({'read_at': rawReadAt}, 'read_at');
    if (!_validNotificationId(id) ||
        title.trim().isEmpty ||
        title.length > 120 ||
        body.trim().isEmpty ||
        body.length > 500 ||
        visibleUntil != createdAt.add(notificationRetention) ||
        (readAt != null && readAt.isBefore(createdAt))) {
      throw const ContractException('invalid notification');
    }
    return MobileNotification(
      id: id,
      type: MobileNotificationTypeWire.parse(json['type']),
      title: title,
      body: body,
      createdAt: createdAt,
      visibleUntil: visibleUntil,
      readAt: readAt,
      destination:
          NotificationDestination.parseOrFallback(json['destination'], id),
    );
  }

  final String id, title, body;
  final MobileNotificationType type;
  final DateTime createdAt, visibleUntil;
  final DateTime? readAt;
  final NotificationDestination destination;
  bool get isRead => readAt != null;
  bool visibleAt(DateTime now) =>
      !createdAt.isAfter(now.toUtc()) && visibleUntil.isAfter(now.toUtc());

  MobileNotification markRead(DateTime value) => MobileNotification(
        id: id,
        type: type,
        title: title,
        body: body,
        createdAt: createdAt,
        visibleUntil: visibleUntil,
        readAt: readAt ?? value.toUtc(),
        destination: destination,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type.wire,
        'title': title,
        'body': body,
        'created_at': createdAt.toUtc().toIso8601String(),
        'visible_until': visibleUntil.toUtc().toIso8601String(),
        'read_at': readAt?.toUtc().toIso8601String(),
        'destination': destination.toJson(),
      };
}

class NotificationPage {
  const NotificationPage(this.items, this.nextCursor);
  factory NotificationPage.fromJson(Map<String, dynamic> json) =>
      NotificationPage(
        _required<List<dynamic>>(json, 'items')
            .map((item) => MobileNotification.fromJson(
                item as Map<String, dynamic>))
            .toList(growable: false),
        _nullable<String>(json, 'next_cursor'),
      );
  final List<MobileNotification> items;
  final String? nextCursor;
}

class NotificationReadResult {
  const NotificationReadResult(this.notificationId, this.readAt, this.changed);
  factory NotificationReadResult.fromJson(Map<String, dynamic> json) {
    final notificationId = _required<String>(json, 'notification_id');
    if (!_validNotificationId(notificationId)) {
      throw const ContractException('invalid notification read id');
    }
    return NotificationReadResult(
      notificationId,
      _utcDate(json, 'read_at'),
      _required(json, 'changed'),
    );
  }
  final String notificationId;
  final DateTime readAt;
  final bool changed;
}

class NotificationReadAllResult {
  const NotificationReadAllResult(this.changedCount, this.unreadCount);
  factory NotificationReadAllResult.fromJson(Map<String, dynamic> json) {
    final changed = _required<int>(json, 'changed_count');
    final unread = _required<int>(json, 'unread_count');
    if (changed < 0 || unread < 0) {
      throw const ContractException('invalid mark-all result');
    }
    return NotificationReadAllResult(changed, unread);
  }
  final int changedCount, unreadCount;
}

class CachedNotificationData {
  const CachedNotificationData(
      this.personId, this.items, this.unreadCount, this.lastSyncedAt);
  final String personId;
  final List<MobileNotification> items;
  final int unreadCount;
  final DateTime lastSyncedAt;
}

class NotificationCache {
  const NotificationCache(this.store, this.installationId);
  final DurableStore store;
  final String installationId;
  String get _prefix => 'notification-cache:v1:$installationId:';
  String get _indexKey => 'notification-cache-index:v1:$installationId';
  String _key(String personId) => '$_prefix$personId';

  Future<void> save(
      Person principal, List<MobileNotification> items, DateTime now,
      {int? unreadCount}) async {
    if (!principal.canReadNotifications) {
      await clear();
      throw const ContractException('notification capability required');
    }
    final previous = await store.read(_indexKey);
    if (previous != null && previous != principal.id) await clear();
    if (items.map((item) => item.id).toSet().length != items.length) {
      await clear();
      throw const ContractException('duplicate notification');
    }
    final visibleUnread = items.where((item) => !item.isRead).length;
    final storedUnread = unreadCount ?? visibleUnread;
    if (storedUnread < visibleUnread) {
      await clear();
      throw const ContractException('invalid notification unread count');
    }
    await store.write(
        _key(principal.id),
        jsonEncode({
          'version': 1,
          'person_id': principal.id,
          'capability': 'notifications:read',
          'items': items.map((item) => item.toJson()).toList(),
          'unread_count': storedUnread,
          'last_synced_at': now.toUtc().toIso8601String(),
        }));
    await store.write(_indexKey, principal.id);
  }

  Future<CachedNotificationData?> loadFor(
      Person principal, DateTime now,
      {required bool sessionPresent}) async {
    if (!sessionPresent || !principal.canReadNotifications) {
      await clear();
      return null;
    }
    final indexedPerson = await store.read(_indexKey);
    if (indexedPerson == null) {
      if (await store.countKeysWithPrefix(_prefix, maximum: 0) != 0) {
        await clear();
      }
      return null;
    }
    if (indexedPerson != principal.id) {
      await clear();
      return null;
    }
    final raw = await store.read(_key(principal.id));
    if (raw == null) {
      await clear();
      return null;
    }
    try {
      final value = jsonDecode(raw) as Map<String, dynamic>;
      if (value['version'] != 1 ||
          value['person_id'] != principal.id ||
          value['capability'] != 'notifications:read') {
        throw const ContractException('notification cache scope mismatch');
      }
      final items = (value['items'] as List<dynamic>)
          .map((item) => MobileNotification.fromJson(
              item as Map<String, dynamic>))
          .where((item) => item.visibleAt(now))
          .toList(growable: false);
      if (items.map((item) => item.id).toSet().length != items.length) {
        throw const ContractException('duplicate cached notification');
      }
      final storedUnreadCount = value['unread_count'];
      final visibleUnreadCount = items.where((item) => !item.isRead).length;
      if (storedUnreadCount is! int || storedUnreadCount < visibleUnreadCount) {
        throw const ContractException('invalid cached unread count');
      }
      return CachedNotificationData(
        principal.id,
        items,
        visibleUnreadCount,
        _utcDate(value, 'last_synced_at'),
      );
    } on Object {
      await clear();
      return null;
    }
  }

  Future<void> clear() async {
    await store.deleteKeysWithPrefix(_prefix);
    await store.delete(_indexKey);
  }

  Future<void> reconcileFreshPrincipal(Person? previous, Person current) async {
    final indexedPerson = await store.read(_indexKey);
    if (!current.canReadNotifications ||
        previous != null && previous.id != current.id ||
        indexedPerson != null && indexedPerson != current.id) {
      await clear();
    }
  }
}

/// A de-identified, bounded local-storage observation for debug evidence.
///
/// A missing input or more than one pending intent is intentionally
/// unobservable: callers must not turn partial local state into evidence.
class CacheSessionAggregate {
  const CacheSessionAggregate({
    required this.sessionPresent,
    required this.basicCachePresent,
    required this.officerReportCachePresent,
    required this.pendingAttendanceIntentPresent,
  });

  final bool sessionPresent;
  final bool basicCachePresent;
  final bool officerReportCachePresent;
  final bool pendingAttendanceIntentPresent;

  static CacheSessionAggregate? resolve({
    required bool? sessionPresent,
    required bool? basicCachePresent,
    required bool? officerReportCachePresent,
    required int? pendingAttendanceIntentCount,
  }) {
    if (sessionPresent == null ||
        basicCachePresent == null ||
        officerReportCachePresent == null ||
        pendingAttendanceIntentCount == null ||
        pendingAttendanceIntentCount < 0 ||
        pendingAttendanceIntentCount > 1) {
      return null;
    }
    return CacheSessionAggregate(
      sessionPresent: sessionPresent,
      basicCachePresent: basicCachePresent,
      officerReportCachePresent: officerReportCachePresent,
      pendingAttendanceIntentPresent: pendingAttendanceIntentCount == 1,
    );
  }

  @override
  bool operator ==(Object other) =>
      other is CacheSessionAggregate &&
      other.sessionPresent == sessionPresent &&
      other.basicCachePresent == basicCachePresent &&
      other.officerReportCachePresent == officerReportCachePresent &&
      other.pendingAttendanceIntentPresent == pendingAttendanceIntentPresent;

  @override
  int get hashCode => Object.hash(
        sessionPresent,
        basicCachePresent,
        officerReportCachePresent,
        pendingAttendanceIntentPresent,
      );
}

enum AttendanceQualification { teamPlayer, guestPlayer }

class RepliedAttendance {
  const RepliedAttendance(
      this.personId, this.displayName, this.reply, this.qualification);
  factory RepliedAttendance.fromJson(Map<String, dynamic> json) =>
      RepliedAttendance(
          _required(json, 'person_id'),
          _required(json, 'display_name'),
          AttendanceReplyWire.parse(json['reply']),
          switch (json['qualification']) {
            'team_player' => AttendanceQualification.teamPlayer,
            'guest_player' => AttendanceQualification.guestPlayer,
            _ =>
              throw const ContractException('unknown attendance qualification'),
          });
  final String personId, displayName;
  final AttendanceReply reply;
  final AttendanceQualification qualification;
}

class AttendanceSnapshot {
  const AttendanceSnapshot(this.gameId, this.ownReply, this.replied);
  factory AttendanceSnapshot.fromJson(Map<String, dynamic> json) {
    final own = _nullable<String>(json, 'own_reply');
    return AttendanceSnapshot(
        _required(json, 'game_id'),
        own == null ? null : AttendanceReplyWire.parse(own),
        _required<List<dynamic>>(json, 'replied')
            .map((item) =>
                RepliedAttendance.fromJson(item as Map<String, dynamic>))
            .toList(growable: false));
  }
  final String gameId;
  final AttendanceReply? ownReply;
  final List<RepliedAttendance> replied;
}

enum NotificationStatus { notRequired, succeeded, failed, unknown }

class MutationNotification {
  const MutationNotification(this.status, this.code);
  factory MutationNotification.fromJson(Map<String, dynamic> json) =>
      MutationNotification(
          switch (json['status']) {
            'not_required' => NotificationStatus.notRequired,
            'succeeded' => NotificationStatus.succeeded,
            'failed' => NotificationStatus.failed,
            'unknown' => NotificationStatus.unknown,
            _ => throw const ContractException('unknown notification status'),
          },
          _nullable(json, 'code'));
  final NotificationStatus status;
  final String? code;
}

class MutationResult {
  const MutationResult(this.gameId, this.reply, this.changed, this.updatedAt,
      this.notification, this.idempotentReplay);
  factory MutationResult.fromJson(Map<String, dynamic> json) => MutationResult(
      _required(json, 'game_id'),
      AttendanceReplyWire.parse(json['reply']),
      _nullable(json, 'changed'),
      _utcDate(json, 'updated_at'),
      MutationNotification.fromJson(
          _required<Map<String, dynamic>>(json, 'notification')),
      _required(json, 'idempotent_replay'));
  final String gameId;
  final AttendanceReply reply;
  final bool? changed;
  final DateTime updatedAt;
  final MutationNotification notification;
  final bool idempotentReplay;
}

class ApiResponse {
  const ApiResponse(this.status, this.body);
  final int status;
  final Map<String, dynamic>? body;
}

abstract interface class ApiTransport {
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {}, Map<String, dynamic>? body});
}

class HttpApiTransport implements ApiTransport {
  HttpApiTransport(this.baseUrl, this.client,
      {this.timeout = const Duration(seconds: 15)});
  final Uri baseUrl;
  final http.Client client;
  final Duration timeout;
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    final request = http.Request(method, baseUrl.resolve('/api/v1$path'))
      ..headers.addAll({
        'Accept': 'application/json',
        if (body != null) 'Content-Type': 'application/json',
        ...headers
      });
    if (body != null) request.body = jsonEncode(body);
    late final http.StreamedResponse response;
    try {
      response = await client.send(request).timeout(timeout);
    } on Object catch (error) {
      if (error is ContractException) rethrow;
      throw const NetworkException();
    }
    late final String text;
    try {
      text = await response.stream.bytesToString().timeout(timeout);
    } on Object catch (error) {
      if (error is ContractException) rethrow;
      throw const NetworkException();
    }
    Object? decoded;
    if (text.isNotEmpty) {
      try {
        decoded = jsonDecode(text);
      } on FormatException {
        throw const ContractException('invalid JSON response');
      }
    }
    if (decoded != null && decoded is! Map<String, dynamic>) {
      throw const ContractException('invalid response shape');
    }
    return ApiResponse(response.statusCode, decoded as Map<String, dynamic>?);
  }
}

abstract interface class DurableStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
  Future<bool> containsKey(String key);
  Future<int> countKeysWithPrefix(String prefix, {required int maximum});
  Future<void> deleteKeysWithPrefix(String prefix);
}

class MemoryStore implements DurableStore {
  final Map<String, String> values = {};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }

  @override
  Future<bool> containsKey(String key) async => values.containsKey(key);

  @override
  Future<int> countKeysWithPrefix(String prefix, {required int maximum}) async {
    if (maximum < 0) throw ArgumentError.value(maximum, 'maximum');
    var count = 0;
    for (final key in values.keys) {
      if (!key.startsWith(prefix)) continue;
      count++;
      if (count > maximum) return maximum + 1;
    }
    return count;
  }

  @override
  Future<void> deleteKeysWithPrefix(String prefix) async {
    values.removeWhere((key, _) => key.startsWith(prefix));
  }
}

class SecureStore implements DurableStore {
  SecureStore()
      : storage = const FlutterSecureStorage(
            aOptions: AndroidOptions(
                storageNamespace: 'ntubtob_mobile_v1',
                migrateWithBackup: false),
            iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device));
  final FlutterSecureStorage storage;
  @override
  Future<String?> read(String key) => storage.read(key: key);
  @override
  Future<void> write(String key, String value) =>
      storage.write(key: key, value: value);
  @override
  Future<void> delete(String key) => storage.delete(key: key);

  @override
  Future<bool> containsKey(String key) => storage.containsKey(key: key);

  @override
  Future<int> countKeysWithPrefix(String prefix, {required int maximum}) async {
    if (maximum < 0) throw ArgumentError.value(maximum, 'maximum');
    var count = 0;
    for (final key in (await storage.readAll()).keys) {
      if (!key.startsWith(prefix)) continue;
      count++;
      if (count > maximum) return maximum + 1;
    }
    return count;
  }

  @override
  Future<void> deleteKeysWithPrefix(String prefix) async {
    final keys = (await storage.readAll())
        .keys
        .where((key) => key.startsWith(prefix))
        .toList(growable: false);
    for (final key in keys) {
      await storage.delete(key: key);
    }
  }
}

class SecureIds {
  SecureIds([Random? random]) : _random = random ?? Random.secure();
  final Random _random;
  String next() => base64Url
      .encode(List<int>.generate(32, (_) => _random.nextInt(256)))
      .replaceAll('=', '');
}

abstract interface class LineLoginPort {
  Future<String> login(String nonce);
  Future<void> logout();
}

class NativeLineLogin implements LineLoginPort {
  NativeLineLogin(this.channelId);
  final String channelId;
  bool _ready = false;
  Future<void> _setup() async {
    if (!_ready) {
      await LineSDK.instance.setup(channelId);
      _ready = true;
    }
  }

  @override
  Future<String> login(String nonce) async {
    await _setup();
    final option = LoginOption(false, 'normal')..idTokenNonce = nonce;
    final result =
        await LineSDK.instance.login(scopes: const ['openid'], option: option);
    final token = result.accessToken.idTokenRaw;
    if (token == null || token.isEmpty || result.idTokenNonce != nonce) {
      throw const ContractException('LINE login result was not nonce-bound');
    }
    return token;
  }

  @override
  Future<void> logout() async {
    await _setup();
    await LineSDK.instance.logout();
  }
}

enum LoginState {
  idle,
  providerActive,
  exchanging,
  authenticated,
  identityPending,
  accountUnavailable,
  cancelled,
  error,
  unavailable,
  timeoutUnresolved,
  timeoutResolved,
  stale,
  duplicate
}

class LoginCoordinator extends ChangeNotifier {
  LoginCoordinator(
      this.line, this.api, this.sessions, this.ids, this.installationId,
      {this.loginTimeout = const Duration(seconds: 35)});
  final LineLoginPort line;
  final ApiTransport api;
  final SessionController sessions;
  final SecureIds ids;
  final String installationId;
  final Duration loginTimeout;
  LoginState state = LoginState.idle;
  String? _active;
  String? _nativeAttempt;
  bool _disposed = false;
  final Set<String> _completed = {};
  bool get nativeFlowUnresolved => _nativeAttempt != null;

  Future<void> login(String platform) async {
    if (platform != 'android' && platform != 'ios') {
      state = LoginState.unavailable;
      _notifyListeners();
      return;
    }
    if (_nativeAttempt != null) {
      state = LoginState.timeoutUnresolved;
      _notifyListeners();
      return;
    }
    final attempt = ids.next(), nonce = ids.next();
    _active = attempt;
    _nativeAttempt = attempt;
    state = LoginState.providerActive;
    _notifyListeners();
    late final Future<String> nativeLogin;
    try {
      nativeLogin = line.login(nonce);
      final token = await nativeLogin.timeout(loginTimeout);
      if (_nativeAttempt != attempt) {
        state = LoginState.stale;
        return;
      }
      _nativeAttempt = null;
      await completeAttemptForTesting(
          attempt: attempt, nonce: nonce, token: token, platform: platform);
    } on PlatformException catch (error) {
      if (_nativeAttempt == attempt) _nativeAttempt = null;
      state = error.code.toLowerCase().contains('cancel')
          ? LoginState.cancelled
          : LoginState.error;
    } on MissingPluginException {
      if (_nativeAttempt == attempt) _nativeAttempt = null;
      state = LoginState.unavailable;
    } on TimeoutException {
      // Expire exchange authority immediately while retaining the separate
      // native lifecycle lock until the SDK future actually settles.
      if (_active == attempt) _active = null;
      state = LoginState.timeoutUnresolved;
      unawaited(_settleTimedOutNativeFlow(attempt, nativeLogin));
    } catch (_) {
      if (_nativeAttempt == attempt) _nativeAttempt = null;
      state = LoginState.error;
    } finally {
      _notifyListeners();
    }
  }

  Future<void> _settleTimedOutNativeFlow(
      String attempt, Future<String> nativeLogin) async {
    LoginState resolvedState;
    try {
      await nativeLogin;
      resolvedState = LoginState.timeoutResolved;
    } on PlatformException catch (error) {
      resolvedState = error.code.toLowerCase().contains('cancel')
          ? LoginState.cancelled
          : LoginState.timeoutResolved;
    } on Object {
      resolvedState = LoginState.timeoutResolved;
    }
    if (_nativeAttempt != attempt) return;
    _nativeAttempt = null;
    _active = null;
    state = resolvedState;
    _notifyListeners();
  }

  void _notifyListeners() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  @visibleForTesting
  Future<void> completeAttemptForTesting(
      {required String attempt,
      required String nonce,
      required String token,
      required String platform}) async {
    if (_active != attempt) {
      state = LoginState.stale;
      return;
    }
    if (!_completed.add(attempt)) {
      state = LoginState.duplicate;
      return;
    }
    state = LoginState.exchanging;
    _notifyListeners();
    final response = await api.send('POST', '/auth/line/exchange', body: {
      'id_token': token,
      'nonce': nonce,
      'login_attempt_id': attempt,
      'installation_id': installationId,
      'platform': platform
    });
    if (response.status != 201 || response.body == null) {
      if (response.body == null) {
        throw const ContractException('missing login error body');
      }
      final error = ApiError.fromJson(response.body!);
      state = switch (error.code) {
        ApiErrorCode.identityPending => LoginState.identityPending,
        ApiErrorCode.accountUnavailable => LoginState.accountUnavailable,
        _ => LoginState.error,
      };
      return;
    }
    await sessions.accept(SessionEnvelope.fromJson(response.body!));
    state = LoginState.authenticated;
  }
}

class SessionController {
  SessionController(this.api, this.store, this.installationId, this.ids,
      {this.terminalPurge});
  final ApiTransport api;
  final DurableStore store;
  final String installationId;
  final SecureIds ids;
  final Future<void> Function()? terminalPurge;
  String? _access;
  Future<String>? _refreshing;
  String? get accessToken => _access;
  Future<bool?> observePresence() async {
    final refreshPresent = await store.containsKey('refresh:$installationId');
    final attemptPresent =
        await store.containsKey('refresh-attempt:$installationId');
    if (!refreshPresent && attemptPresent) return null;
    return refreshPresent;
  }

  Future<void> accept(SessionEnvelope session) async {
    try {
      await store.write('refresh:$installationId', session.refreshToken);
      await store.delete('refresh-attempt:$installationId');
      _access = session.accessToken;
    } on Object {
      _access = null;
      await store.delete('refresh:$installationId');
      rethrow;
    }
  }

  Future<String> refresh() =>
      _refreshing ??= _refresh().whenComplete(() => _refreshing = null);
  Future<String> _refresh() async {
    final refresh = await store.read('refresh:$installationId');
    if (refresh == null) throw StateError('signed out');
    final attemptKey = 'refresh-attempt:$installationId';
    final attempt = await store.read(attemptKey) ?? ids.next();
    await store.write(attemptKey, attempt);
    final response = await api.send('POST', '/auth/refresh',
        headers: {'Refresh-Attempt-ID': attempt},
        body: {'refresh_token': refresh, 'installation_id': installationId});
    if (response.status == 401) {
      await clear();
      throw const SessionExpiredException();
    }
    if (response.status != 200 || response.body == null) {
      throw StateError('refresh uncertain');
    }
    final session = SessionEnvelope.fromJson(response.body!);
    await accept(session);
    return session.accessToken;
  }

  Future<ApiResponse> authorized(String method, String path,
      {Map<String, dynamic>? body,
      Map<String, String> headers = const {}}) async {
    var token = _access ?? await refresh();
    final failedToken = token;
    var result = await _sendAuthorizedRequest(method, path, token,
        headers: headers, body: body);
    if (result.status == 401) {
      token = _access != null && _access != failedToken
          ? _access!
          : await refresh();
      result = await _sendAuthorizedRequest(method, path, token,
          headers: headers, body: body);
      if (result.status == 401) {
        await clear();
        if (result.body != null) {
          final error = ApiError.fromJson(result.body!);
          if (error.code != ApiErrorCode.sessionExpired &&
              error.code != ApiErrorCode.unauthenticated) {
            throw error;
          }
        }
        throw const SessionExpiredException();
      }
    }
    return result;
  }

  Future<ApiResponse> _sendAuthorizedRequest(
      String method, String path, String token,
      {Map<String, dynamic>? body,
      Map<String, String> headers = const {}}) async {
    try {
      return await api.send(method, path,
          headers: {...headers, 'Authorization': 'Bearer $token'}, body: body);
    } on NetworkException {
      throw const AuthorizedRequestNetworkException();
    }
  }

  Future<void> clear() async {
    _access = null;
    await store.delete('refresh:$installationId');
    await store.delete('refresh-attempt:$installationId');
    await terminalPurge?.call();
  }

  Future<void> logout(
    LineLoginPort line, {
    Future<void> Function()? purgeLocal,
  }) async {
    await store.write('logout-pending:$installationId', 'true');
    final durableSessionPresent =
        await store.containsKey('refresh:$installationId');
    if (_access != null || durableSessionPresent) {
      ApiResponse response;
      try {
        response = await authorized('POST', '/auth/logout');
      } on SessionExpiredException {
        // A terminal refresh 401 already cleared the local session and is an
        // idempotent logout outcome. Transient refresh failures retain state.
        if (await store.containsKey('refresh:$installationId')) rethrow;
        response = const ApiResponse(401, null);
      }
      if (response.status != 204 && response.status != 401) {
        throw StateError('logout pending');
      }
    }
    await clear();
    try {
      await line.logout();
    } catch (_) {/* backend session is already closed */}
    await purgeLocal?.call();
    await store.delete('logout-pending:$installationId');
  }
}

class MutationPendingException implements Exception {
  const MutationPendingException(this.reply);
  final AttendanceReply reply;
}

class MutationUncertainException implements Exception {
  const MutationUncertainException(this.reply);
  final AttendanceReply reply;
}

class OfflineReadOnlyException implements Exception {
  const OfflineReadOnlyException();
}

abstract interface class NotificationClient {
  Future<List<MobileNotification>> notifications({bool unreadOnly = false});
  Future<MobileNotification> notification(String id);
  Future<int> unreadCount();
  Future<NotificationReadResult> markRead(String id);
  Future<NotificationReadAllResult> markAllRead();
}

abstract interface class NotificationPublishingClient {
  Future<Map<String, dynamic>> preview(Map<String, dynamic> draft);
  Future<Map<String, dynamic>> confirm(
      Map<String, dynamic> draft, Map<String, dynamic> preview, String key);
}

class OfficerNotificationPublisher implements NotificationPublishingClient {
  const OfficerNotificationPublisher(this.session, this.principal);
  final SessionController session;
  final Person principal;

  void _requireCapability() {
    if (!principal.canPublishNotifications) {
      throw const ContractException('notification publishing capability required');
    }
  }

  Never _failure(ApiResponse response) {
    if (response.body != null) throw ApiError.fromJson(response.body!);
    throw const ContractException('notification publishing response missing');
  }

  @override
  Future<Map<String, dynamic>> preview(Map<String, dynamic> draft) async {
    _requireCapability();
    final response = await session.authorized(
        'POST', '/officer/notifications/preview', body: draft);
    if (response.status != 200 || response.body == null) _failure(response);
    final body = response.body!;
    final count = _required<int>(body, 'recipient_count');
    final revision = _required<String>(body, 'revision');
    final confirmation = _required<String>(body, 'confirmation_text');
    if (count < 1 || count > 500 ||
        !RegExp(r'^[0-9a-f]{64}$').hasMatch(revision) ||
        confirmation != 'PUBLISH $count') {
      throw const ContractException('invalid notification preview');
    }
    return Map.unmodifiable(body);
  }

  @override
  Future<Map<String, dynamic>> confirm(
      Map<String, dynamic> draft, Map<String, dynamic> preview, String key) async {
    _requireCapability();
    if (key.length < 16 || key.length > 200) {
      throw const ContractException('invalid publishing idempotency key');
    }
    final response = await session.authorized(
        'POST', '/officer/notifications/confirm',
        headers: {'Idempotency-Key': key},
        body: {
          'draft': draft,
          'preview_revision': _required<String>(preview, 'revision'),
          'typed_confirmation': _required<String>(preview, 'confirmation_text'),
        });
    if (!{200, 201}.contains(response.status) || response.body == null) {
      _failure(response);
    }
    return Map.unmodifiable(response.body!);
  }

  Future<Map<String, dynamic>> registerFakeDevice({
    required String installationId,
    required String platform,
    required String fakeToken,
  }) async {
    final response = await session.authorized('PUT', '/devices/current', body: {
      'installation_id': installationId,
      'platform': platform,
      'provider': 'fake',
      'token': fakeToken,
    });
    if (response.status != 200 || response.body == null) _failure(response);
    return Map.unmodifiable(response.body!);
  }

  Future<Map<String, dynamic>> revokeDevice(String installationId) async {
    final response = await session.authorized('DELETE', '/devices/current',
        body: {'installation_id': installationId});
    if (response.status != 200 || response.body == null) _failure(response);
    return Map.unmodifiable(response.body!);
  }
}

class NotificationApi implements NotificationClient {
  const NotificationApi(this.session);
  final SessionController session;

  Never _failure(ApiResponse response, String operation) {
    if (response.body != null) throw ApiError.fromJson(response.body!);
    throw ContractException('missing $operation response body');
  }

  Future<NotificationPage> page(
      {String? cursor, bool unreadOnly = false}) async {
    final query = <String>['limit=100'];
    if (cursor != null) {
      query.add('cursor=${Uri.encodeQueryComponent(cursor)}');
    }
    if (unreadOnly) query.add('unread_only=true');
    final result = await session.authorized(
        'GET', '/notifications?${query.join('&')}');
    if (result.status != 200 || result.body == null) {
      _failure(result, 'notifications');
    }
    return NotificationPage.fromJson(result.body!);
  }

  @override
  Future<List<MobileNotification>> notifications(
      {bool unreadOnly = false}) async {
    final items = <MobileNotification>[];
    final ids = <String>{};
    final cursors = <String>{};
    String? cursor;
    do {
      final result = await page(cursor: cursor, unreadOnly: unreadOnly);
      for (final item in result.items) {
        if (!ids.add(item.id)) {
          throw const ContractException('duplicate notification page item');
        }
        items.add(item);
      }
      cursor = result.nextCursor;
      if (cursor != null && !cursors.add(cursor)) {
        throw const ContractException('repeated notification cursor');
      }
    } while (cursor != null);
    return List.unmodifiable(items);
  }

  @override
  Future<MobileNotification> notification(String id) async {
    final result = await session.authorized(
        'GET', '/notifications/${Uri.encodeComponent(id)}');
    if (result.status != 200 || result.body == null) {
      _failure(result, 'notification');
    }
    return MobileNotification.fromJson(result.body!);
  }

  @override
  Future<int> unreadCount() async {
    final result =
        await session.authorized('GET', '/notifications/unread-count');
    if (result.status != 200 || result.body == null) {
      _failure(result, 'notification unread count');
    }
    final count = _required<int>(result.body!, 'unread_count');
    if (count < 0) throw const ContractException('invalid unread count');
    return count;
  }

  @override
  Future<NotificationReadResult> markRead(String id) async {
    final result = await session.authorized(
        'PUT', '/notifications/${Uri.encodeComponent(id)}/read',
        body: const {});
    if (result.status != 200 || result.body == null) {
      _failure(result, 'notification mark read');
    }
    final parsed = NotificationReadResult.fromJson(result.body!);
    if (parsed.notificationId != id) {
      throw const ContractException('notification read id mismatch');
    }
    return parsed;
  }

  @override
  Future<NotificationReadAllResult> markAllRead() async {
    final result = await session.authorized(
        'PUT', '/notifications/read-all', body: const {});
    if (result.status != 200 || result.body == null) {
      _failure(result, 'notification mark all read');
    }
    return NotificationReadAllResult.fromJson(result.body!);
  }
}

class BasicApi {
  BasicApi(this.session, this.store, this.installationId, this.ids);
  final SessionController session;
  final DurableStore store;
  final String installationId;
  final SecureIds ids;
  Future<int> observePendingAttendanceIntentCount() =>
      store.countKeysWithPrefix(
        'mutation:$installationId:',
        maximum: 1,
      );

  Future<void> clearPendingAttendanceIntents() =>
      store.deleteKeysWithPrefix('mutation:$installationId:');
  Never _failure(ApiResponse response, String operation) {
    if (response.body != null) throw ApiError.fromJson(response.body!);
    throw ContractException('missing $operation response body');
  }

  Future<Person> me() async {
    final r = await session.authorized('GET', '/me');
    if (r.status != 200 || r.body == null) _failure(r, 'me');
    return Person.fromJson(r.body!);
  }

  Future<GamePage> gamePage({String? cursor}) async {
    final path = cursor == null
        ? '/games'
        : '/games?cursor=${Uri.encodeQueryComponent(cursor)}';
    final r = await session.authorized('GET', path);
    if (r.status != 200 || r.body == null) _failure(r, 'games');
    return GamePage.fromJson(r.body!);
  }

  Future<List<Game>> games() async {
    final result = <Game>[];
    final seen = <String>{};
    String? cursor;
    do {
      final page = await gamePage(cursor: cursor);
      result.addAll(page.items);
      cursor = page.nextCursor;
      if (cursor != null && !seen.add(cursor)) {
        throw const ContractException('repeated games cursor');
      }
    } while (cursor != null);
    return result;
  }

  Future<Game> game(String id) async {
    final r =
        await session.authorized('GET', '/games/${Uri.encodeComponent(id)}');
    if (r.status != 200 || r.body == null) _failure(r, 'game');
    return Game.fromJson(r.body!);
  }

  Future<AttendanceSnapshot> attendance(String id) async {
    final r = await session.authorized(
        'GET', '/games/${Uri.encodeComponent(id)}/attendance');
    if (r.status != 200 || r.body == null) {
      _failure(r, 'attendance');
    }
    return AttendanceSnapshot.fromJson(r.body!);
  }

  Future<AttendanceReport> attendanceReport(String id,
      {int historyLimit = 12, int minimumResponseRate = 60}) async {
    if (!const {5, 8, 12, 20}.contains(historyLimit) ||
        !_percentage(minimumResponseRate) ||
        minimumResponseRate % 10 != 0) {
      throw const ContractException('invalid report query');
    }
    final path = '/games/${Uri.encodeComponent(id)}/attendance-report'
        '?history_limit=$historyLimit'
        '&minimum_response_rate=$minimumResponseRate';
    final r = await session.authorized('GET', path);
    if (r.status != 200 || r.body == null) _failure(r, 'attendance report');
    return AttendanceReport.fromJson(r.body!);
  }

  Future<MutationResult> reply(String gameId, AttendanceReply reply,
      {required bool online}) async {
    if (!online) throw const OfflineReadOnlyException();
    final keyName = 'mutation:$installationId:$gameId';
    final existing = await store.read(keyName);
    String key;
    if (existing == null) {
      key = ids.next();
    } else {
      final intent = jsonDecode(existing) as Map<String, dynamic>;
      final pendingReply = AttendanceReplyWire.parse(intent['reply']);
      key = _required<String>(intent, 'key');
      if (pendingReply != reply) {
        final snapshot = await attendance(gameId);
        if (snapshot.ownReply == pendingReply) {
          await store.delete(keyName);
          key = ids.next();
        } else {
          throw MutationPendingException(pendingReply);
        }
      }
    }
    await store.write(keyName,
        jsonEncode({'key': key, 'reply': reply.wire, 'uncertain': true}));
    late final ApiResponse r;
    try {
      r = await session.authorized(
          'PUT', '/games/${Uri.encodeComponent(gameId)}/attendance-reply',
          headers: {'Idempotency-Key': key}, body: {'reply': reply.wire});
    } on AuthorizedRequestNetworkException {
      return _reconcileUncertainMutation(gameId, reply, keyName);
    }
    if (r.status >= 500) {
      return _reconcileUncertainMutation(gameId, reply, keyName);
    }
    if (r.status != 200 || r.body == null) _failure(r, 'mutation');
    final result = MutationResult.fromJson(r.body!);
    await store.delete(keyName);
    return result;
  }

  Future<MutationResult> _reconcileUncertainMutation(
      String gameId, AttendanceReply reply, String keyName) async {
    try {
      final snapshot = await attendance(gameId);
      if (snapshot.ownReply == reply) {
        await store.delete(keyName);
        return MutationResult(
            gameId,
            reply,
            null,
            DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
            const MutationNotification(
                NotificationStatus.unknown, 'outcome_unknown'),
            true);
      }
    } on MutationUncertainException {
      rethrow;
    } on Object {
      // No authoritative proof: preserve the logical intent and its key.
    }
    throw MutationUncertainException(reply);
  }
}
