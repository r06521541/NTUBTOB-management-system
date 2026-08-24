import 'dart:convert';

import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_theme.dart';
import 'integration.dart';

/// Local presentation input derived by a future canonical adapter.
///
/// This is intentionally not a wire capability or DTO.
class ManagementReportReadGrant {
  const ManagementReportReadGrant._(this.isGranted);

  const ManagementReportReadGrant.granted() : this._(true);
  const ManagementReportReadGrant.denied() : this._(false);

  final bool isGranted;
}

enum ManagementPresentationRoute {
  home,
  schedule,
  notifications,
  account,
  reportsHub,
  singleGameReport,
}

class RealModePresentationPolicy {
  const RealModePresentationPolicy(this.reportReadGrant);

  final ManagementReportReadGrant reportReadGrant;

  List<ManagementPresentationRoute> get bottomDestinations => [
        ManagementPresentationRoute.home,
        ManagementPresentationRoute.schedule,
        ManagementPresentationRoute.notifications,
        ManagementPresentationRoute.account,
        if (reportReadGrant.isGranted) ManagementPresentationRoute.reportsHub,
      ];

  bool canReach(ManagementPresentationRoute route) => switch (route) {
        ManagementPresentationRoute.home ||
        ManagementPresentationRoute.schedule ||
        ManagementPresentationRoute.notifications ||
        ManagementPresentationRoute.account =>
          true,
        ManagementPresentationRoute.reportsHub ||
        ManagementPresentationRoute.singleGameReport =>
          reportReadGrant.isGranted,
      };
}

/// Flutter-local display model. It is not a server response or wire DTO.
class ReportParticipantUiModel {
  const ReportParticipantUiModel({
    required this.id,
    required this.displayName,
    this.reply,
    this.memberNumber,
  });

  final String id;
  final String displayName;
  final AttendanceReply? reply;
  final int? memberNumber;

  String get replyAnnotation => switch (reply) {
        AttendanceReply.arrivingLate => '晚到',
        AttendanceReply.leavingEarly => '早走',
        _ => '',
      };

  bool get fineEligible =>
      reply == AttendanceReply.attending ||
      reply == AttendanceReply.leavingEarly;
}

class NotYetRepliedUiModel extends ReportParticipantUiModel {
  const NotYetRepliedUiModel({
    required super.id,
    required super.displayName,
    required this.observedReplies,
    required this.observedGames,
    required this.responseRate,
    required this.participationRate,
    required this.nonparticipationRate,
  });

  final int observedReplies,
      observedGames,
      responseRate,
      participationRate,
      nonparticipationRate;
}

/// Flutter-local single-game report model. It defines no JSON field names.
class SingleGameReportUiModel {
  const SingleGameReportUiModel({
    required this.gameId,
    required this.gameLabel,
    required this.generatedAt,
    required this.historyGames,
    required this.historyLimit,
    required this.minimumResponseRate,
    required this.attending,
    required this.notAttending,
    required this.notYetReplied,
  });

  final String gameId;
  final String gameLabel;
  final DateTime generatedAt;
  final int historyGames, historyLimit, minimumResponseRate;
  final List<ReportParticipantUiModel> attending, notAttending;
  final List<NotYetRepliedUiModel> notYetReplied;
}

class AttendanceInsights {
  const AttendanceInsights(this.report);

  final SingleGameReportUiModel report;

  int get attending => report.attending.length;
  int get unavailable => report.notAttending.length;
  int get unanswered => report.notYetReplied.length;
  int get total => attending + unavailable + unanswered;
  int get responded => attending + unavailable;
  int get responsePercent => total == 0 ? 0 : (responded * 100 ~/ total);
  int get availabilityPercent =>
      responded == 0 ? 0 : (attending * 100 ~/ responded);
  bool get isSmallSample => total < 5;

  String callout({required bool offline}) {
    if (total == 0) return '尚無回覆資料，暫時無法形成名單建議。';
    final source = offline ? '離線快取，可能過期；' : '';
    final sample = isSmallSample ? '樣本很少，' : '';
    if (unanswered > 0) {
      return '$source$sample尚有 $unanswered 人未回覆，先以目前已回覆名單規劃。';
    }
    return '$source$sample目前 $attending 人表示可出席；這僅是已載入回覆的整理。';
  }
}

class LineupDraft {
  factory LineupDraft.fromReport(SingleGameReportUiModel report) {
    final seen = <String>{};
    final pool = report.attending
        .where((player) => seen.add(player.id))
        .toList(growable: false);
    return LineupDraft._(pool, report.notYetReplied.length);
  }

  LineupDraft._(List<ReportParticipantUiModel> pool, this.unansweredCount)
      : _pool = List.of(pool);

  LineupDraft.copy(LineupDraft other)
      : _pool = List.of(other._pool),
        unansweredCount = other.unansweredCount {
    coarseRoles.addAll(other.coarseRoles);
    coarseCoaches.addAll(other.coarseCoaches);
    fineCoaches.addAll(other.fineCoaches);
    fieldAssignments.addAll(other.fieldAssignments);
    battingOrder.addAll(other.battingOrder);
  }

  final List<ReportParticipantUiModel> _pool;
  final int unansweredCount;
  final Map<String, CoarseLineupRole> coarseRoles = {};
  final Set<String> coarseCoaches = {};
  final Set<String> fineCoaches = {};
  final Map<LineupFieldPosition, ReportParticipantUiModel> fieldAssignments =
      {};
  final Map<int, ReportParticipantUiModel> battingOrder = {};

  List<ReportParticipantUiModel> get pool => List.unmodifiable(_pool);
  int get missingStarterCount => 9 - battingOrder.length;
  bool get isReady => battingOrder.length == 9 && unansweredCount == 0;
  bool get hasUniqueFieldAssignments {
    final ids = fieldAssignments.values.map((player) => player.id).toList();
    return ids.toSet().length == ids.length;
  }

  bool get hasUniqueBattingOrder {
    final ids = battingOrder.values.map((player) => player.id).toList();
    return ids.toSet().length == ids.length;
  }

  List<ReportParticipantUiModel> get fineEligiblePlayers =>
      _pool.where((player) => player.fineEligible).toList(growable: false);

  List<ReportParticipantUiModel> get battingCandidates {
    final assigned = fieldAssignments.values.toSet();
    final pitcher = nonBattingPitcher;
    return fineEligiblePlayers
        .where(assigned.contains)
        .where((player) => player.id != pitcher?.id)
        .toList(growable: false);
  }

  List<ReportParticipantUiModel> get reserves => _pool
      .where((player) => !fieldAssignments.values.contains(player))
      .toList(growable: false);

  int get fineUnassignedCount => _pool
      .where((player) => player.id != nonBattingPitcher?.id)
      .where((player) => !battingOrder.values.contains(player))
      .length;

  void assignBattingSlot(int slot, ReportParticipantUiModel? player) {
    if (slot < 1 || slot > 9) return;
    if (player == null) {
      battingOrder.remove(slot);
      return;
    }
    if (!battingCandidates.contains(player)) return;
    battingOrder.removeWhere((_, assigned) => assigned.id == player.id);
    battingOrder[slot] = player;
  }

  void assignCoarseRole(
    ReportParticipantUiModel player,
    CoarseLineupRole role,
  ) {
    if (!pool.contains(player)) return;
    if (coarseRoles[player.id] == role) {
      coarseRoles.remove(player.id);
    } else {
      coarseRoles[player.id] = role;
    }
  }

  void assignFieldPosition(
    LineupFieldPosition position,
    ReportParticipantUiModel? player,
  ) {
    if (player == null) {
      final removed = fieldAssignments.remove(position);
      if (removed != null) _removeFromBatting(removed);
      return;
    }
    if (!pool.contains(player) || !player.fineEligible) return;
    final replaced = fieldAssignments[position];
    if (replaced != null && replaced.id != player.id) {
      _removeFromBatting(replaced);
    }
    fieldAssignments.removeWhere((_, assigned) => assigned.id == player.id);
    fieldAssignments[position] = player;
    _enforceDhPitcherRule();
  }

  void _enforceDhPitcherRule() {
    if (!fieldAssignments.containsKey(LineupFieldPosition.designatedHitter)) {
      return;
    }
    final pitcher = fieldAssignments[LineupFieldPosition.pitcher];
    if (pitcher != null) _removeFromBatting(pitcher);
  }

  void _removeFromBatting(ReportParticipantUiModel player) =>
      battingOrder.removeWhere((_, assigned) => assigned.id == player.id);

  ReportParticipantUiModel? get nonBattingPitcher =>
      fieldAssignments.containsKey(LineupFieldPosition.designatedHitter)
          ? fieldAssignments[LineupFieldPosition.pitcher]
          : null;

  void resetCoarse() {
    coarseRoles.clear();
    coarseCoaches.clear();
  }

  void resetFine() {
    fieldAssignments.clear();
    battingOrder.clear();
    fineCoaches.clear();
  }

  void clearAll() {
    resetCoarse();
    resetFine();
  }
}

enum LineupLabMode { batting, reserves }

enum LineupPlanningMode { coarse, fine }

enum LineupResetScope { coarse, fine, all }

enum CoarseLineupRole { pitcher, catcher, infield, outfield }

enum LineupFieldPosition {
  pitcher('P'),
  catcher('C'),
  firstBase('1B'),
  secondBase('2B'),
  thirdBase('3B'),
  shortstop('SS'),
  leftField('LF'),
  centerField('CF'),
  rightField('RF'),
  designatedHitter('DH');

  const LineupFieldPosition(this.label);
  final String label;
}

abstract interface class LineupSummaryCopyPort {
  Future<void> copy(String summary);
}

class SystemLineupSummaryCopyPort implements LineupSummaryCopyPort {
  const SystemLineupSummaryCopyPort();

  @override
  Future<void> copy(String summary) =>
      Clipboard.setData(ClipboardData(text: summary));
}

abstract interface class OfficerReportPresentationPort {
  Future<SingleGameReportUiModel> readSingleGame({
    required String principalId,
    required String gameId,
  });
}

class CanonicalOfficerReportRepository
    implements OfficerReportPresentationPort {
  const CanonicalOfficerReportRepository(this.api);

  final BasicApi api;

  @override
  Future<SingleGameReportUiModel> readSingleGame({
    required String principalId,
    required String gameId,
  }) async {
    try {
      final report = await api.attendanceReport(gameId);
      return SingleGameReportUiModel(
        gameId: report.gameId,
        gameLabel: '賽事 ${report.gameId}',
        generatedAt: report.generatedAt,
        historyGames: report.observation.historyGames,
        historyLimit: report.observation.historyLimit,
        minimumResponseRate: report.observation.minimumResponseRate,
        attending: report.attending
            .map((person) => ReportParticipantUiModel(
                  id: person.personId,
                  displayName: person.displayName,
                  reply: person.reply,
                  memberNumber: person.memberNumber,
                ))
            .toList(growable: false),
        notAttending: report.notAttending
            .map((person) => ReportParticipantUiModel(
                  id: person.personId,
                  displayName: person.displayName,
                  reply: person.reply,
                  memberNumber: person.memberNumber,
                ))
            .toList(growable: false),
        notYetReplied: report.notYetReplied
            .map((person) => NotYetRepliedUiModel(
                  id: person.personId,
                  displayName: person.displayName,
                  observedReplies: person.observedReplies,
                  observedGames: person.observedGames,
                  responseRate: person.responseRate,
                  participationRate: person.participationRate,
                  nonparticipationRate: person.nonparticipationRate,
                ))
            .toList(growable: false),
      );
    } on NetworkException {
      throw const RetryableOfficerReportException();
    } on SessionExpiredException {
      throw const ExpiredOfficerReportSessionException();
    } on ApiError catch (error) {
      if (error.code == ApiErrorCode.forbidden ||
          error.code == ApiErrorCode.resourceNotFound) {
        throw const ForbiddenOfficerReportException();
      }
      if (error.code == ApiErrorCode.sessionExpired ||
          error.code == ApiErrorCode.unauthenticated) {
        throw const ExpiredOfficerReportSessionException();
      }
      if (error.retryable) throw const RetryableOfficerReportException();
      throw const ContractOfficerReportException();
    } on ContractException {
      throw const ContractOfficerReportException();
    }
  }
}

class RetryableOfficerReportException implements Exception {
  const RetryableOfficerReportException();
}

class ForbiddenOfficerReportException implements Exception {
  const ForbiddenOfficerReportException();
}

class ExpiredOfficerReportSessionException implements Exception {
  const ExpiredOfficerReportSessionException();
}

class ContractOfficerReportException implements Exception {
  const ContractOfficerReportException();
}

class DeterministicFakeOfficerReportRepository
    implements OfficerReportPresentationPort {
  DeterministicFakeOfficerReportRepository({
    SingleGameReportUiModel? report,
    this.failure,
  }) : report =
            report ?? DeterministicFakeOfficerReportRepository.fictionalReport;

  static final fictionalReport = SingleGameReportUiModel(
    gameId: 'fictional-game',
    gameLabel: '示範賽事',
    generatedAt: DateTime.utc(2026, 8, 19),
    historyGames: 8,
    historyLimit: 12,
    minimumResponseRate: 60,
    attending: [
      ReportParticipantUiModel(
        id: 'fictional-replied',
        displayName: '已回覆隊員',
        memberNumber: 18,
      ),
    ],
    notAttending: [],
    notYetReplied: [
      NotYetRepliedUiModel(
        id: 'fictional-not-yet-replied',
        displayName: '尚未回覆隊員',
        observedReplies: 7,
        observedGames: 8,
        responseRate: 88,
        participationRate: 63,
        nonparticipationRate: 25,
      ),
    ],
  );

  final SingleGameReportUiModel report;
  final Object? failure;
  final List<(String, String)> reads = [];

  @override
  Future<SingleGameReportUiModel> readSingleGame({
    required String principalId,
    required String gameId,
  }) async {
    reads.add((principalId, gameId));
    if (failure case final failure?) throw failure;
    return report;
  }
}

abstract interface class PrincipalOfficerReportCache {
  Future<SingleGameReportUiModel?> read(String principalId, String gameId);
  Future<void> write(String principalId, SingleGameReportUiModel report);
  Future<void> clearPrincipal(String principalId);
}

Future<void> reconcileFreshReportPrincipal({
  required PrincipalOfficerReportCache cache,
  required Person? previous,
  required Person current,
}) async {
  if (previous == null) return;
  final identityChanged = previous.id != current.id;
  final accessLevelDowngraded =
      current.accessLevel.index < previous.accessLevel.index;
  final grantRevoked =
      previous.canReadAttendanceReport && !current.canReadAttendanceReport;
  if (identityChanged || accessLevelDowngraded || grantRevoked) {
    await cache.clearPrincipal(previous.id);
  }
}

class InMemoryPrincipalOfficerReportCache
    implements PrincipalOfficerReportCache {
  final Map<String, SingleGameReportUiModel> _values = {};
  final List<String> clearedPrincipals = [];

  String _key(String principalId, String gameId) => '$principalId::$gameId';

  @override
  Future<SingleGameReportUiModel?> read(
    String principalId,
    String gameId,
  ) async =>
      _values[_key(principalId, gameId)];

  @override
  Future<void> write(String principalId, SingleGameReportUiModel report) async {
    _values[_key(principalId, report.gameId)] = report;
  }

  @override
  Future<void> clearPrincipal(String principalId) async {
    _values.removeWhere((key, _) => key.startsWith('$principalId::'));
    clearedPrincipals.add(principalId);
  }
}

class DurablePrincipalOfficerReportCache
    implements PrincipalOfficerReportCache {
  const DurablePrincipalOfficerReportCache(this.store, this.installationId);

  static const _version = 1;
  static const _maximumReports = 20;
  static const maximumEncodedBytes = 65536;
  static const _maximumIdCharacters = 256;
  static const _maximumLabelCharacters = 300;
  static const _maximumDisplayNameCharacters = 120;
  final DurableStore store;
  final String installationId;

  String _key(String principalId) =>
      'officer-report-cache:v1:$installationId:${Uri.encodeComponent(principalId)}';

  String get _installationPrefix => 'officer-report-cache:v1:$installationId:';

  Future<bool> observeAnyPresence() async =>
      await store.countKeysWithPrefix(_installationPrefix, maximum: 0) > 0;

  Future<void> clearInstallation() =>
      store.deleteKeysWithPrefix(_installationPrefix);

  @override
  Future<SingleGameReportUiModel?> read(
      String principalId, String gameId) async {
    final reports = await _readAll(principalId);
    for (final report in reports) {
      if (report.gameId == gameId) return report;
    }
    return null;
  }

  @override
  Future<void> write(String principalId, SingleGameReportUiModel report) async {
    _validate(report);
    final reports = await _readAll(principalId);
    reports.removeWhere((item) => item.gameId == report.gameId);
    reports.add(report);
    if (reports.length > _maximumReports) {
      reports.removeRange(0, reports.length - _maximumReports);
    }
    final encoded = jsonEncode({
      'version': _version,
      'reports': reports.map(_encode).toList(growable: false),
    });
    if (utf8.encode(encoded).length > maximumEncodedBytes) {
      throw const FormatException('report cache capacity exceeded');
    }
    await store.write(_key(principalId), encoded);
  }

  @override
  Future<void> clearPrincipal(String principalId) =>
      store.delete(_key(principalId));

  Future<List<SingleGameReportUiModel>> _readAll(String principalId) async {
    final key = _key(principalId);
    final raw = await store.read(key);
    if (raw == null) return [];
    try {
      if (utf8.encode(raw).length > maximumEncodedBytes) {
        throw const FormatException('oversized report cache');
      }
      final value = jsonDecode(raw) as Map<String, dynamic>;
      if (value['version'] != _version) {
        throw const FormatException('unknown cache version');
      }
      final values = value['reports'] as List<dynamic>;
      if (values.length > _maximumReports) {
        throw const FormatException('unbounded report cache');
      }
      return values
          .map((item) => _decode(item as Map<String, dynamic>))
          .toList(growable: true);
    } on Object {
      await store.delete(key);
      return [];
    }
  }

  static Map<String, dynamic> _encode(SingleGameReportUiModel report) => {
        'game_id': report.gameId,
        'game_label': report.gameLabel,
        'generated_at': report.generatedAt.toUtc().toIso8601String(),
        'history_games': report.historyGames,
        'history_limit': report.historyLimit,
        'minimum_response_rate': report.minimumResponseRate,
        'attending': report.attending.map(_encodeParticipant).toList(),
        'not_attending': report.notAttending.map(_encodeParticipant).toList(),
        'not_yet_replied': report.notYetReplied
            .map((person) => {
                  ..._encodeParticipant(person),
                  'observed_replies': person.observedReplies,
                  'observed_games': person.observedGames,
                  'response_rate': person.responseRate,
                  'participation_rate': person.participationRate,
                  'nonparticipation_rate': person.nonparticipationRate,
                })
            .toList(),
      };

  static Map<String, dynamic> _encodeParticipant(
          ReportParticipantUiModel person) =>
      {
        'id': person.id,
        'display_name': person.displayName,
        if (person.reply != null) 'reply': person.reply!.wire,
        if (person.memberNumber != null) 'member_number': person.memberNumber,
      };

  static SingleGameReportUiModel _decode(Map<String, dynamic> value) {
    final generatedAt = DateTime.parse(value['generated_at'] as String);
    if (!generatedAt.isUtc) throw const FormatException('non-UTC cache time');
    final report = SingleGameReportUiModel(
      gameId: value['game_id'] as String,
      gameLabel: value['game_label'] as String,
      generatedAt: generatedAt,
      historyGames: value['history_games'] as int,
      historyLimit: value['history_limit'] as int,
      minimumResponseRate: value['minimum_response_rate'] as int,
      attending: _decodeParticipants(value['attending']),
      notAttending: _decodeParticipants(value['not_attending']),
      notYetReplied: (value['not_yet_replied'] as List<dynamic>).map((item) {
        final person = item as Map<String, dynamic>;
        return NotYetRepliedUiModel(
          id: person['id'] as String,
          displayName: person['display_name'] as String,
          observedReplies: person['observed_replies'] as int,
          observedGames: person['observed_games'] as int,
          responseRate: person['response_rate'] as int,
          participationRate: person['participation_rate'] as int,
          nonparticipationRate: person['nonparticipation_rate'] as int,
        );
      }).toList(growable: false),
    );
    _validate(report);
    return report;
  }

  static void _validate(SingleGameReportUiModel report) {
    if (!_validText(report.gameId, _maximumIdCharacters) ||
        !_validText(report.gameLabel, _maximumLabelCharacters) ||
        report.historyGames < 0 ||
        !const {5, 8, 12, 20}.contains(report.historyLimit) ||
        report.minimumResponseRate < 0 ||
        report.minimumResponseRate > 100 ||
        report.minimumResponseRate % 10 != 0 ||
        report.attending.length +
                report.notAttending.length +
                report.notYetReplied.length >
            200 ||
        [...report.attending, ...report.notAttending].any((person) =>
            !_validText(person.id, _maximumIdCharacters) ||
            !_validText(person.displayName, _maximumDisplayNameCharacters) ||
            (person.memberNumber != null &&
                (person.memberNumber! < 0 || person.memberNumber! > 999))) ||
        report.notYetReplied.any((person) =>
            !_validText(person.id, _maximumIdCharacters) ||
            !_validText(person.displayName, _maximumDisplayNameCharacters) ||
            person.observedReplies < 1 ||
            person.observedGames < 1 ||
            !_validPercentage(person.responseRate) ||
            !_validPercentage(person.participationRate) ||
            !_validPercentage(person.nonparticipationRate))) {
      throw const FormatException('invalid cached report');
    }
  }

  static bool _validPercentage(int value) => value >= 0 && value <= 100;
  static bool _validText(String value, int maximumCharacters) =>
      value.isNotEmpty && value.runes.length <= maximumCharacters;

  static List<ReportParticipantUiModel> _decodeParticipants(Object? value) =>
      (value as List<dynamic>).map((item) {
        final person = item as Map<String, dynamic>;
        return ReportParticipantUiModel(
          id: person['id'] as String,
          displayName: person['display_name'] as String,
          reply: person['reply'] == null
              ? null
              : AttendanceReplyWire.parse(person['reply']),
          memberNumber: person['member_number'] as int?,
        );
      }).toList(growable: false);
}

enum OfficerReportViewState {
  loading,
  empty,
  ready,
  retryableError,
  forbidden,
  sessionExpired,
  contractError,
  offlineCached,
}

enum OfficerReportLoadProvenance { freshServer, offlineCache }

enum CanonicalOfficerReportState { ready, empty, offlineCachedReadonly }

class OfficerReportController extends ChangeNotifier {
  OfficerReportController({
    required this.repository,
    required this.cache,
    this.lineupSummaryCopyPort = const SystemLineupSummaryCopyPort(),
  });

  final OfficerReportPresentationPort repository;
  final PrincipalOfficerReportCache cache;
  final LineupSummaryCopyPort lineupSummaryCopyPort;

  String? _principalId;
  ManagementReportReadGrant _grant = const ManagementReportReadGrant.denied();
  ManagementPresentationRoute _route = ManagementPresentationRoute.home;
  OfficerReportViewState state = OfficerReportViewState.empty;
  SingleGameReportUiModel? report;
  DateTime? lastSyncedAt;
  OfficerReportLoadProvenance? _loadProvenance;
  LineupDraft? _lineupDraft;
  String? _lineupDraftGameId;

  String? get principalId => _principalId;
  ManagementPresentationRoute get route => _route;
  RealModePresentationPolicy get policy => RealModePresentationPolicy(_grant);
  bool get mutationsEnabled => false;

  LineupDraft lineupDraftFor(SingleGameReportUiModel report) {
    if (_lineupDraft == null || _lineupDraftGameId != report.gameId) {
      _lineupDraft = LineupDraft.fromReport(report);
      _lineupDraftGameId = report.gameId;
    }
    return _lineupDraft!;
  }

  Future<void> applyFreshPrincipal({
    required String principalId,
    required ManagementReportReadGrant reportReadGrant,
  }) async {
    final previousPrincipal = _principalId;
    final identityChanged =
        previousPrincipal != null && previousPrincipal != principalId;
    final downgraded = previousPrincipal == principalId &&
        _grant.isGranted &&
        !reportReadGrant.isGranted;
    if (identityChanged) await cache.clearPrincipal(previousPrincipal);
    if (downgraded) await cache.clearPrincipal(principalId);
    _principalId = principalId;
    _grant = reportReadGrant;
    if (identityChanged || downgraded || !reportReadGrant.isGranted) {
      _revokePresentation();
    }
    notifyListeners();
  }

  bool open(ManagementPresentationRoute requested) {
    if (!policy.canReach(requested)) {
      _revokePresentation();
      notifyListeners();
      return false;
    }
    _route = requested;
    notifyListeners();
    return true;
  }

  Future<void> loadSingleGame(
    String gameId, {
    required bool online,
    DateTime? syncedAt,
  }) async {
    final principal = _principalId;
    if (principal == null ||
        !policy.canReach(ManagementPresentationRoute.singleGameReport)) {
      _revokePresentation();
      state = OfficerReportViewState.forbidden;
      notifyListeners();
      return;
    }
    _route = ManagementPresentationRoute.singleGameReport;
    state = OfficerReportViewState.loading;
    _loadProvenance = null;
    notifyListeners();
    if (!online) {
      final cached = await cache.read(principal, gameId);
      report = cached;
      state = cached == null
          ? OfficerReportViewState.retryableError
          : OfficerReportViewState.offlineCached;
      _loadProvenance =
          cached == null ? null : OfficerReportLoadProvenance.offlineCache;
      notifyListeners();
      return;
    }
    try {
      final loaded = await repository.readSingleGame(
        principalId: principal,
        gameId: gameId,
      );
      report = loaded;
      lastSyncedAt = (syncedAt ?? DateTime.now()).toUtc();
      await cache.write(principal, loaded);
      state = loaded.attending.isEmpty &&
              loaded.notAttending.isEmpty &&
              loaded.notYetReplied.isEmpty &&
              loaded.historyGames == 0
          ? OfficerReportViewState.empty
          : OfficerReportViewState.ready;
      _loadProvenance = OfficerReportLoadProvenance.freshServer;
    } on ForbiddenOfficerReportException {
      await cache.clearPrincipal(principal);
      _revokePresentation();
      state = OfficerReportViewState.forbidden;
    } on ExpiredOfficerReportSessionException {
      await cache.clearPrincipal(principal);
      _revokePresentation();
      state = OfficerReportViewState.sessionExpired;
    } on RetryableOfficerReportException {
      state = OfficerReportViewState.retryableError;
    } on ContractOfficerReportException {
      state = OfficerReportViewState.contractError;
    }
    notifyListeners();
  }

  void _revokePresentation() {
    _route = ManagementPresentationRoute.home;
    report = null;
    _lineupDraft = null;
    _lineupDraftGameId = null;
    lastSyncedAt = null;
    _loadProvenance = null;
  }
}

class OfficerReadOnlyShell extends StatelessWidget {
  const OfficerReadOnlyShell({super.key, required this.controller});

  final OfficerReportController controller;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: controller,
        builder: (context, _) {
          final destinations = controller.policy.bottomDestinations;
          return Scaffold(
            appBar: AppBar(title: const Text('隊務報表')),
            body: switch (controller.route) {
              ManagementPresentationRoute.home =>
                const Center(child: Text('首頁')),
              ManagementPresentationRoute.schedule =>
                const Center(child: Text('賽程')),
              ManagementPresentationRoute.notifications =>
                const Center(child: Text('通知')),
              ManagementPresentationRoute.account =>
                const Center(child: Text('帳號')),
              ManagementPresentationRoute.reportsHub => _ReportHub(controller),
              ManagementPresentationRoute.singleGameReport =>
                OfficerReportPanel(
                  controller: controller,
                ),
            },
            bottomNavigationBar: NavigationBar(
              selectedIndex: switch (controller.route) {
                ManagementPresentationRoute.home => 0,
                ManagementPresentationRoute.schedule => 1,
                ManagementPresentationRoute.notifications => 2,
                ManagementPresentationRoute.account => 3,
                ManagementPresentationRoute.reportsHub ||
                ManagementPresentationRoute.singleGameReport =>
                  4,
              },
              onDestinationSelected: (index) =>
                  controller.open(destinations[index]),
              destinations: [
                for (final destination in destinations)
                  NavigationDestination(
                    icon: Icon(switch (destination) {
                      ManagementPresentationRoute.home => Icons.home_outlined,
                      ManagementPresentationRoute.schedule =>
                        Icons.event_outlined,
                      ManagementPresentationRoute.notifications =>
                        Icons.notifications_outlined,
                      ManagementPresentationRoute.account =>
                        Icons.person_outline,
                      ManagementPresentationRoute.reportsHub =>
                        Icons.assessment_outlined,
                      ManagementPresentationRoute.singleGameReport =>
                        throw StateError('detail is not a bottom destination'),
                    }),
                    label: switch (destination) {
                      ManagementPresentationRoute.home => '首頁',
                      ManagementPresentationRoute.schedule => '賽程',
                      ManagementPresentationRoute.notifications => '通知',
                      ManagementPresentationRoute.account => '帳號',
                      ManagementPresentationRoute.reportsHub => '管理',
                      ManagementPresentationRoute.singleGameReport =>
                        throw StateError('detail is not a bottom destination'),
                    },
                  ),
              ],
            ),
          );
        },
      );
}

class CanonicalManagementReportsPage extends StatefulWidget {
  const CanonicalManagementReportsPage({
    super.key,
    required this.api,
    required this.person,
    required this.games,
    required this.online,
    this.cache,
  });

  final BasicApi api;
  final Person person;
  final List<Game> games;
  final bool online;
  final PrincipalOfficerReportCache? cache;

  @override
  State<CanonicalManagementReportsPage> createState() =>
      _CanonicalManagementReportsPageState();
}

class _CanonicalManagementReportsPageState
    extends State<CanonicalManagementReportsPage> {
  late final OfficerReportController controller;

  @override
  void initState() {
    super.initState();
    controller = OfficerReportController(
      repository: CanonicalOfficerReportRepository(widget.api),
      cache: widget.cache ?? InMemoryPrincipalOfficerReportCache(),
    );
    controller.applyFreshPrincipal(
      principalId: widget.person.id,
      reportReadGrant: widget.person.canReadAttendanceReport
          ? const ManagementReportReadGrant.granted()
          : const ManagementReportReadGrant.denied(),
    );
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('出席報表')),
        body: !widget.person.canReadAttendanceReport
            ? Semantics(
                key: const ValueKey('management-route-forbidden'),
                label: '沒有報表讀取權限',
                child: const Center(child: Text('沒有報表讀取權限')),
              )
            : ListenableBuilder(
                listenable: controller,
                builder: (context, _) => controller.route ==
                            ManagementPresentationRoute.singleGameReport ||
                        const {
                          OfficerReportViewState.forbidden,
                          OfficerReportViewState.sessionExpired,
                          OfficerReportViewState.contractError,
                        }.contains(controller.state)
                    ? OfficerReportPanel(controller: controller)
                    : ListView(
                        children: [
                          if (!widget.online)
                            const ListTile(
                              leading: Icon(Icons.cloud_off),
                              title: Text('離線唯讀模式'),
                            ),
                          if (widget.games.isEmpty)
                            const ListTile(title: Text('目前沒有賽事')),
                          for (final game in widget.games)
                            ListTile(
                              key: ValueKey('report-game-${game.id}'),
                              leading: const Icon(Icons.fact_check_outlined),
                              title: Text(
                                '${game.homeTeam ?? '主隊'} vs '
                                '${game.awayTeam ?? '客隊'}',
                              ),
                              subtitle: const Text('唯讀出席報表'),
                              onTap: () => controller.loadSingleGame(
                                game.id,
                                online: widget.online,
                              ),
                            ),
                        ],
                      ),
              ),
      );
}

class _ReportHub extends StatelessWidget {
  const _ReportHub(this.controller);

  final OfficerReportController controller;

  @override
  Widget build(BuildContext context) => ListTile(
        key: const ValueKey('single-game-report-entry'),
        leading: const Icon(Icons.fact_check_outlined),
        title: const Text('單場出席報表'),
        subtitle: const Text('唯讀'),
        onTap: () =>
            controller.open(ManagementPresentationRoute.singleGameReport),
      );
}

class OfficerReportPanel extends StatelessWidget {
  const OfficerReportPanel({
    super.key,
    required this.controller,
    this.diagnosticEnabled = true,
  });

  final OfficerReportController controller;
  final bool diagnosticEnabled;

  @override
  Widget build(BuildContext context) {
    final semantics = switch (controller.state) {
      OfficerReportViewState.loading => '報表載入中',
      OfficerReportViewState.empty => '此賽事目前沒有回覆資料',
      OfficerReportViewState.ready => '單場出席報表',
      OfficerReportViewState.retryableError => '報表暫時無法載入，請重試',
      OfficerReportViewState.forbidden => '沒有報表讀取權限',
      OfficerReportViewState.sessionExpired => '登入已逾期，報表已關閉',
      OfficerReportViewState.contractError => '報表資料格式異常，已停止處理',
      OfficerReportViewState.offlineCached => '離線快取唯讀報表',
    };
    final diagnosticState =
        DebugOfficerReportProjection.fromController(controller);
    final showDiagnostic = diagnosticState != null &&
        DebugOfficerReportProjection.shouldRender(
          debugBuild: kDebugMode,
          diagnosticEnabled: diagnosticEnabled,
        );
    final content = switch (controller.state) {
      OfficerReportViewState.loading => const Center(
          child: CircularProgressIndicator(),
        ),
      OfficerReportViewState.ready ||
      OfficerReportViewState.offlineCached =>
        _ReportContents(
          report: controller.report!,
          offline: controller.state == OfficerReportViewState.offlineCached,
          controller: controller,
        ),
      _ => Center(child: Text(semantics)),
    };
    return Semantics(
      key: ValueKey('officer-report-${controller.state.name}'),
      label: semantics,
      liveRegion: true,
      child: showDiagnostic
          ? Column(
              children: [
                DebugOfficerReportProjection(state: diagnosticState),
                Expanded(child: content),
              ],
            )
          : content,
    );
  }
}

class DebugOfficerReportProjection extends StatelessWidget {
  const DebugOfficerReportProjection({super.key, required this.state});

  final CanonicalOfficerReportState state;

  static bool shouldRender({
    required bool debugBuild,
    required bool diagnosticEnabled,
  }) =>
      debugBuild && diagnosticEnabled;

  static CanonicalOfficerReportState? canonicalState({
    required bool freshReady,
    required bool freshEmpty,
    required bool offlineCachedReadonly,
    required int enabledWriteControlCount,
  }) {
    if (enabledWriteControlCount != 0) return null;
    final candidates = <CanonicalOfficerReportState>[
      if (freshReady) CanonicalOfficerReportState.ready,
      if (freshEmpty) CanonicalOfficerReportState.empty,
      if (offlineCachedReadonly)
        CanonicalOfficerReportState.offlineCachedReadonly,
    ];
    return candidates.length == 1 ? candidates.single : null;
  }

  static CanonicalOfficerReportState? fromController(
    OfficerReportController controller,
  ) {
    final report = controller.report;
    final reportIsEmpty = report != null &&
        report.attending.isEmpty &&
        report.notAttending.isEmpty &&
        report.notYetReplied.isEmpty &&
        report.historyGames == 0;
    return canonicalState(
      freshReady: controller.state == OfficerReportViewState.ready &&
          controller._loadProvenance ==
              OfficerReportLoadProvenance.freshServer &&
          report != null &&
          !reportIsEmpty,
      freshEmpty: controller.state == OfficerReportViewState.empty &&
          controller._loadProvenance ==
              OfficerReportLoadProvenance.freshServer &&
          reportIsEmpty,
      offlineCachedReadonly:
          controller.state == OfficerReportViewState.offlineCached &&
              controller._loadProvenance ==
                  OfficerReportLoadProvenance.offlineCache &&
              report != null,
      enabledWriteControlCount: controller.mutationsEnabled ? 1 : 0,
    );
  }

  String get _token => switch (state) {
        CanonicalOfficerReportState.ready => 'ready',
        CanonicalOfficerReportState.empty => 'empty',
        CanonicalOfficerReportState.offlineCachedReadonly =>
          'offline_cached_readonly',
      };

  @override
  Widget build(BuildContext context) => Semantics(
        key: const ValueKey('debug-officer-report-projection'),
        label: '偵錯報表投影：$_token；已啟用寫入控制：0',
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Text('$_token；已啟用寫入控制：0'),
        ),
      );
}

class _ReportContents extends StatefulWidget {
  const _ReportContents({
    required this.report,
    required this.offline,
    required this.controller,
  });

  final SingleGameReportUiModel report;
  final bool offline;
  final OfficerReportController controller;

  @override
  State<_ReportContents> createState() => _ReportContentsState();
}

class _ReportContentsState extends State<_ReportContents> {
  late LineupDraft _draft;

  @override
  void initState() {
    super.initState();
    _draft = widget.controller.lineupDraftFor(widget.report);
  }

  @override
  void didUpdateWidget(covariant _ReportContents oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.report.gameId != widget.report.gameId) {
      _draft = widget.controller.lineupDraftFor(widget.report);
    }
  }

  @override
  Widget build(BuildContext context) {
    final report = widget.report;
    final insights = AttendanceInsights(report);
    return Material(
      child: ListView(
        children: [
          Text(report.gameLabel),
          Text('產生時間：${report.generatedAt.toUtc().toIso8601String()}'),
          Text('觀察場次：${report.historyGames} / ${report.historyLimit}'),
          Text('最低回覆率：${report.minimumResponseRate}%'),
          if (widget.offline) const Text('目前為離線快取，僅供讀取'),
          _InsightsCard(insights: insights, offline: widget.offline),
          ListTile(
            key: const ValueKey('lineup-lab-entry'),
            leading: const Icon(Icons.groups_outlined),
            title: const Text('Lineup Lab'),
            subtitle: const Text('僅供本次規劃，不會提交或儲存'),
            onTap: report.attending.isEmpty
                ? null
                : () async {
                    final updated = await Navigator.of(context)
                        .push<LineupDraft>(MaterialPageRoute(
                      builder: (_) => _LineupLabPage(
                        draft: _draft,
                        offline: widget.offline,
                        copyPort: widget.controller.lineupSummaryCopyPort,
                      ),
                    ));
                    if (updated != null && mounted) {
                      setState(() => _draft = updated);
                    }
                  },
          ),
          const Text('出席'),
          for (final participant in report.attending)
            Text(participant.displayName),
          const Text('不出席'),
          for (final participant in report.notAttending)
            Text(participant.displayName),
          const Text('尚未回覆'),
          for (final participant in report.notYetReplied)
            ListTile(
              title: Text(participant.displayName),
              subtitle: Text(
                '已觀察 ${participant.observedGames} 場、'
                '已回覆 ${participant.observedReplies} 場；'
                '回覆率 ${participant.responseRate}%；'
                '出席率 ${participant.participationRate}%；'
                '不出席率 ${participant.nonparticipationRate}%',
              ),
            ),
        ],
      ),
    );
  }
}

class _InsightsCard extends StatelessWidget {
  const _InsightsCard({required this.insights, required this.offline});
  final AttendanceInsights insights;
  final bool offline;

  @override
  Widget build(BuildContext context) => AppSurfaceCard(
        key: const ValueKey('attendance-insights'),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('出席洞察'),
            Text(
                '可出席 ${insights.attending} 人・不出席 ${insights.unavailable} 人・未回覆 ${insights.unanswered} 人'),
            Text(
                '回覆率 ${insights.responsePercent}%・已回覆者可出席比例 ${insights.availabilityPercent}%'),
            if (insights.isSmallSample) const Text('樣本很少，僅供目前回覆的整理。'),
            Text(insights.callout(offline: offline)),
          ]),
        ),
      );
}

class _LineupLabPage extends StatefulWidget {
  const _LineupLabPage({
    required this.draft,
    required this.offline,
    required this.copyPort,
  });
  final LineupDraft draft;
  final bool offline;
  final LineupSummaryCopyPort copyPort;

  @override
  State<_LineupLabPage> createState() => _DecisionLineupLabPageState();
}

class _DecisionLineupLabPageState extends State<_LineupLabPage> {
  late LineupDraft _draft;
  LineupPlanningMode _planningMode = LineupPlanningMode.coarse;
  LineupLabMode _mode = LineupLabMode.batting;
  String? _lastCopiedSummary;
  bool _copyFailed = false;

  @override
  void initState() {
    super.initState();
    _draft = widget.draft;
  }

  @override
  Widget build(BuildContext context) => PopScope<LineupDraft>(
        canPop: false,
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) Navigator.of(context).pop(_draft);
        },
        child: Scaffold(
          appBar: AppBar(
            title: const Text('Lineup Lab'),
            leading:
                BackButton(onPressed: () => Navigator.of(context).pop(_draft)),
          ),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text('這是本次開啟期間的規劃草稿，不是正式提交，也不會儲存或分享。'),
              if (widget.offline) const Text('離線唯讀來源可能過期；這份草稿仍只留在本次開啟期間。'),
              const SizedBox(height: 12),
              _decisionSummary(),
              const SizedBox(height: 12),
              SegmentedButton<LineupPlanningMode>(
                key: const ValueKey('lineup-planning-mode'),
                segments: const [
                  ButtonSegment(
                      value: LineupPlanningMode.coarse, label: Text('粗排')),
                  ButtonSegment(
                      value: LineupPlanningMode.fine, label: Text('細排')),
                ],
                selected: {_planningMode},
                onSelectionChanged: (selection) =>
                    setState(() => _planningMode = selection.single),
              ),
              Wrap(
                children: [
                  TextButton(
                    key: const ValueKey('lineup-reset-coarse'),
                    onPressed: () => _confirmReset(LineupResetScope.coarse),
                    child: const Text('重設粗排'),
                  ),
                  TextButton(
                    key: const ValueKey('lineup-reset-fine'),
                    onPressed: () => _confirmReset(LineupResetScope.fine),
                    child: const Text('重設細排'),
                  ),
                  TextButton(
                    key: const ValueKey('lineup-clear-all'),
                    onPressed: () => _confirmReset(LineupResetScope.all),
                    child: const Text('清除全部排陣'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (_planningMode == LineupPlanningMode.coarse) ..._coarsePanel(),
              if (_planningMode == LineupPlanningMode.fine) ...[
                SegmentedButton<LineupLabMode>(
                  key: const ValueKey('lineup-mode-switch'),
                  segments: [
                    ButtonSegment(
                      value: LineupLabMode.batting,
                      label: Text('棒次 ${_draft.battingOrder.length}/9'),
                    ),
                    ButtonSegment(
                      value: LineupLabMode.reserves,
                      label: Text('候補／未安排 ${_draft.fineUnassignedCount}'),
                    ),
                  ],
                  selected: {_mode},
                  onSelectionChanged: (selection) =>
                      setState(() => _mode = selection.single),
                ),
                _coachPanel(coarse: false),
                const SizedBox(height: 12),
                if (_mode == LineupLabMode.batting) ..._starterSlots(),
                if (_mode == LineupLabMode.reserves) ..._benchPlayers(),
                const SizedBox(height: 12),
                _fieldPanel(),
              ],
              _summaryPreview(),
            ],
          ),
        ),
      );

  List<Widget> _coarsePanel() => [
        const Text('每位可出席球員可先粗分為投手、捕手、內野或外野。'),
        _coachPanel(coarse: true),
        for (final player in _draft.pool)
          Card(
            key: ValueKey('lineup-coarse-${player.id}'),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_annotatedName(player)),
                  Wrap(
                    spacing: 6,
                    children: [
                      for (final role in CoarseLineupRole.values)
                        ChoiceChip(
                          key: ValueKey(
                              'lineup-coarse-${player.id}-${role.name}'),
                          label: Text(_coarseRoleLabel(role)),
                          selected: _draft.coarseRoles[player.id] == role,
                          onSelected: (_) => setState(
                              () => _draft.assignCoarseRole(player, role)),
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ),
      ];

  Widget _coachPanel({required bool coarse}) {
    final coaches = coarse ? _draft.coarseCoaches : _draft.fineCoaches;
    return Card(
      key: ValueKey(coarse ? 'lineup-coarse-coaches' : 'lineup-fine-coaches'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            const Text('教練'),
            for (final player in _draft.pool)
              FilterChip(
                key: ValueKey(
                    'lineup-${coarse ? 'coarse' : 'fine'}-coach-${player.id}'),
                label: Text(_annotatedName(player)),
                selected: coaches.contains(player.id),
                onSelected: (selected) => setState(() {
                  if (selected) {
                    coaches.add(player.id);
                  } else {
                    coaches.remove(player.id);
                  }
                }),
              ),
          ],
        ),
      ),
    );
  }

  Widget _fieldPanel() => Card(
        key: const ValueKey('lineup-field'),
        color: Theme.of(context).colorScheme.secondaryContainer,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('守備配置'),
              const Text('同一球員只會佔一個守位；有 DH 時，投手不列入九棒。'),
              GridView.count(
                crossAxisCount: 3,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  for (final position in LineupFieldPosition.values)
                    OutlinedButton(
                      key: ValueKey('lineup-position-${position.label}'),
                      onPressed: () => _choosePosition(position),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(position.label),
                          Text(
                            _draft.fieldAssignments[position] == null
                                ? '未安排'
                                : _annotatedName(
                                    _draft.fieldAssignments[position]!),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                ],
              ),
              if (_draft.nonBattingPitcher != null)
                ListTile(
                  key: const ValueKey('lineup-non-batting-pitcher'),
                  title: const Text('非打擊投手'),
                  subtitle: Text(_annotatedName(_draft.nonBattingPitcher!)),
                ),
            ],
          ),
        ),
      );

  Future<void> _choosePosition(LineupFieldPosition position) async {
    final selected = await showDialog<Object?>(
      context: context,
      builder: (context) => SimpleDialog(
        key: ValueKey('lineup-position-dialog-${position.label}'),
        title: Text('安排 ${position.label}'),
        children: [
          SimpleDialogOption(
            key: const ValueKey('lineup-position-clear'),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('清除此守位'),
          ),
          for (final player in _draft.pool)
            SimpleDialogOption(
              key: ValueKey(
                  'lineup-position-${position.label}-player-${player.id}'),
              onPressed: player.fineEligible
                  ? () => Navigator.of(context).pop(player)
                  : null,
              child: Text(player.fineEligible
                  ? _annotatedName(player)
                  : '${_annotatedName(player)}（細排不可用：非準時／早走或狀態未載入）'),
            ),
        ],
      ),
    );
    if (!mounted || selected == null) return;
    setState(() => _draft.assignFieldPosition(
          position,
          selected == false ? null : selected as ReportParticipantUiModel,
        ));
  }

  Future<void> _chooseBattingSlot(int slot) async {
    final selected = await showDialog<Object?>(
      context: context,
      builder: (context) => SimpleDialog(
        key: ValueKey('lineup-batting-dialog-$slot'),
        title: Text('安排第 $slot 棒'),
        children: [
          SimpleDialogOption(
            key: ValueKey('lineup-batting-clear-$slot'),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('清除此棒次'),
          ),
          if (_draft.battingCandidates.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('目前沒有已安排守位且符合細排資格的球員。'),
            ),
          for (final player in _draft.battingCandidates)
            SimpleDialogOption(
              key: ValueKey('lineup-batting-$slot-player-${player.id}'),
              onPressed: () => Navigator.of(context).pop(player),
              child: Text(
                '${_annotatedName(player)}（${_positionFor(player)!.label}'
                '${_battingSlotFor(player) == null ? '' : '・目前第 ${_battingSlotFor(player)} 棒'}）',
              ),
            ),
        ],
      ),
    );
    if (!mounted || selected == null) return;
    setState(() => _draft.assignBattingSlot(
          slot,
          selected == false ? null : selected as ReportParticipantUiModel,
        ));
  }

  LineupFieldPosition? _positionFor(ReportParticipantUiModel player) {
    for (final entry in _draft.fieldAssignments.entries) {
      if (entry.value.id == player.id) return entry.key;
    }
    return null;
  }

  int? _battingSlotFor(ReportParticipantUiModel player) {
    for (final entry in _draft.battingOrder.entries) {
      if (entry.value.id == player.id) return entry.key;
    }
    return null;
  }

  Widget _summaryPreview() {
    final summary = _planningMode == LineupPlanningMode.coarse
        ? _coarseSummary()
        : _fineSummary();
    return Card(
      key: const ValueKey('lineup-summary-preview'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('摘要預覽'),
            SelectableText(summary, key: const ValueKey('lineup-summary-text')),
            TextButton.icon(
              key: const ValueKey('lineup-copy-summary'),
              onPressed: () async {
                try {
                  await widget.copyPort.copy(summary);
                  if (mounted) {
                    setState(() {
                      _lastCopiedSummary = summary;
                      _copyFailed = false;
                    });
                  }
                } catch (_) {
                  if (mounted) {
                    setState(() {
                      _lastCopiedSummary = null;
                      _copyFailed = true;
                    });
                  }
                }
              },
              icon: const Icon(Icons.copy_outlined),
              label: Text(_copyFailed
                  ? '無法複製'
                  : _lastCopiedSummary == summary
                      ? '已複製'
                      : '複製摘要'),
            ),
          ],
        ),
      ),
    );
  }

  String _coarseSummary() {
    final coaches = _draft.pool
        .where((player) => _draft.coarseCoaches.contains(player.id))
        .map(_annotatedName)
        .join('、');
    final lines = <String>[
      '粗排摘要',
      '教練：${coaches.isEmpty ? '—' : coaches}',
    ];
    for (final role in CoarseLineupRole.values) {
      final people = _draft.pool
          .where((player) => _draft.coarseRoles[player.id] == role)
          .map(_annotatedName)
          .join('、');
      lines.add('${_coarseRoleLabel(role)}：${people.isEmpty ? '—' : people}');
    }
    final unassigned = _draft.pool
        .where((player) => !_draft.coarseRoles.containsKey(player.id))
        .map(_annotatedName)
        .join('、');
    lines.add('尚未分組：${unassigned.isEmpty ? '—' : unassigned}');
    return lines.join('\n');
  }

  String _fineSummary() {
    final positionById = <String, String>{
      for (final entry in _draft.fieldAssignments.entries)
        entry.value.id: entry.key.label,
    };
    final coaches = _draft.pool
        .where((player) => _draft.fineCoaches.contains(player.id))
        .map(_annotatedName)
        .join('、');
    final lines = <String>[
      '細排摘要',
      '教練：${coaches.isEmpty ? '—' : coaches}',
    ];
    for (var slot = 1; slot <= 9; slot++) {
      final player = _draft.battingOrder[slot];
      lines.add(
          '$slot棒：${player == null ? '—' : '${_annotatedName(player)}（${positionById[player.id]!}）'}');
    }
    if (_draft.nonBattingPitcher != null) {
      lines.add('非打擊投手：${_annotatedName(_draft.nonBattingPitcher!)}');
    }
    final reserves = _draft.reserves.map(_annotatedName).join('、');
    lines.add('候補／未安排：${reserves.isEmpty ? '—' : reserves}');
    return lines.join('\n');
  }

  String _annotatedName(ReportParticipantUiModel player) =>
      '${player.displayName}${player.memberNumber == null ? '' : ' #${player.memberNumber}'}'
      '${player.replyAnnotation.isEmpty ? '' : '（${player.replyAnnotation}）'}';

  String _coarseRoleLabel(CoarseLineupRole role) => switch (role) {
        CoarseLineupRole.pitcher => '投手',
        CoarseLineupRole.catcher => '捕手',
        CoarseLineupRole.infield => '內野',
        CoarseLineupRole.outfield => '外野',
      };

  Widget _decisionSummary() {
    final colors = Theme.of(context).colorScheme;
    final ready = _draft.isReady;
    return Card(
      key: ValueKey(ready ? 'lineup-ready' : 'lineup-warning'),
      color: ready ? colors.secondaryContainer : colors.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(ready ? '名單已齊備' : '名單仍需確認'),
            Text(
              '先發 ${_draft.battingOrder.length}/9・缺 ${_draft.missingStarterCount} 人・'
              '候補／未安排 ${_draft.fineUnassignedCount} 人・尚未回覆 ${_draft.unansweredCount} 人',
              key: const ValueKey('lineup-decision-counts'),
            ),
            Text(
              ready
                  ? '九位先發已排定，且目前沒有尚未回覆者。'
                  : _draft.missingStarterCount > 0
                      ? '先發尚缺 ${_draft.missingStarterCount} 人；此草稿不是正式提交。'
                      : '先發已滿，但仍有人尚未回覆；請保留判斷空間。',
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _starterSlots() => [
        for (var index = 0; index < 9; index++)
          Semantics(
            key: ValueKey('lineup-slot-${index + 1}'),
            label:
                '第 ${index + 1} 棒${_draft.battingOrder[index + 1] == null ? '尚未安排' : ''}',
            child: Card(
              key: _draft.battingOrder[index + 1] == null
                  ? ValueKey('lineup-empty-slot-${index + 1}')
                  : ValueKey(
                      'lineup-batting-${index + 1}-${_draft.battingOrder[index + 1]!.id}'),
              child: ListTile(
                leading: CircleAvatar(child: Text('${index + 1}')),
                title: Text(_draft.battingOrder[index + 1] == null
                    ? '未安排'
                    : _annotatedName(_draft.battingOrder[index + 1]!)),
                subtitle: Text(_draft.battingOrder[index + 1] == null
                    ? '先安排守位，再選擇本棒球員'
                    : _positionFor(_draft.battingOrder[index + 1]!)?.label ??
                        '守位已失效'),
                trailing: OutlinedButton(
                  key: ValueKey('lineup-batting-select-${index + 1}'),
                  onPressed: () => _chooseBattingSlot(index + 1),
                  child: Text(
                      _draft.battingOrder[index + 1] == null ? '選擇' : '更換／清除'),
                ),
              ),
            ),
          ),
      ];

  List<Widget> _benchPlayers() => [
        if (_draft.reserves.isEmpty &&
            _draft.battingCandidates
                .every((player) => _draft.battingOrder.values.contains(player)))
          const Card(
            key: ValueKey('lineup-bench-empty'),
            child: ListTile(title: Text('目前沒有候補或未安排球員')),
          ),
        for (final player in _draft.battingCandidates
            .where((player) => !_draft.battingOrder.values.contains(player)))
          ListTile(
            key: ValueKey('lineup-unbatted-${player.id}'),
            title: Text(_annotatedName(player)),
            subtitle: Text('${_positionFor(player)!.label}・已有守位，尚未排入棒次'),
          ),
        for (final player in _draft.reserves)
          ListTile(
            key: ValueKey('lineup-reserve-${player.id}'),
            title: Text(_annotatedName(player)),
            subtitle: const Text('候補／尚未安排守位'),
          ),
      ];

  Future<void> _confirmReset(LineupResetScope scope) async {
    final label = switch (scope) {
      LineupResetScope.coarse => '粗排',
      LineupResetScope.fine => '細排',
      LineupResetScope.all => '全部排陣',
    };
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        key: const ValueKey('lineup-reset-dialog'),
        title: Text('重設$label？'),
        content: Text('只會重設這次開啟期間的$label，不會提交或儲存正式名單。'),
        actions: [
          TextButton(
            key: const ValueKey('lineup-reset-cancel'),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            key: const ValueKey('lineup-reset-confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('確認重設'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      setState(() {
        switch (scope) {
          case LineupResetScope.coarse:
            _draft.resetCoarse();
            break;
          case LineupResetScope.fine:
            _draft.resetFine();
            _mode = LineupLabMode.batting;
            break;
          case LineupResetScope.all:
            _draft.clearAll();
            _mode = LineupLabMode.batting;
            break;
        }
      });
    }
  }
}
