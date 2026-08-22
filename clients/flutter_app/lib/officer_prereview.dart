import 'dart:convert';

import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';

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
  const ReportParticipantUiModel({required this.id, required this.displayName});

  final String id;
  final String displayName;
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
  int get availabilityPercent => responded == 0 ? 0 : (attending * 100 ~/ responded);
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
  LineupDraft.fromReport(SingleGameReportUiModel report)
      : starters = List.of(report.attending.take(9)),
        bench = List.of(report.attending.skip(9)),
        _pool = List.of(report.attending);

  LineupDraft.copy(LineupDraft other)
      : starters = List.of(other.starters),
        bench = List.of(other.bench),
        _pool = List.of(other._pool);

  final List<ReportParticipantUiModel> starters;
  final List<ReportParticipantUiModel> bench;
  final List<ReportParticipantUiModel> _pool;

  List<ReportParticipantUiModel> get pool => List.unmodifiable(_pool);

  void moveStarter(int from, int to) {
    if (from < 0 || from >= starters.length || to < 0 || to >= starters.length) return;
    final player = starters.removeAt(from);
    starters.insert(to, player);
  }

  void moveToBench(ReportParticipantUiModel player) {
    if (starters.remove(player) && !bench.contains(player)) bench.add(player);
  }

  void addStarter(ReportParticipantUiModel player) {
    if (!pool.contains(player)) return;
    bench.remove(player);
    if (!starters.contains(player)) starters.add(player);
  }

  void reset() {
    starters
      ..clear()
      ..addAll(_pool.take(9));
    bench
      ..clear()
      ..addAll(_pool.skip(9));
  }
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
                id: person.personId, displayName: person.displayName))
            .toList(growable: false),
        notAttending: report.notAttending
            .map((person) => ReportParticipantUiModel(
                id: person.personId, displayName: person.displayName))
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
      ReportParticipantUiModel(id: 'fictional-replied', displayName: '已回覆隊員'),
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
      {'id': person.id, 'display_name': person.displayName};

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
            !_validText(person.displayName, _maximumDisplayNameCharacters)) ||
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
  OfficerReportController({required this.repository, required this.cache});

  final OfficerReportPresentationPort repository;
  final PrincipalOfficerReportCache cache;

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
                        ),
                      ));
                      if (updated != null && mounted) setState(() => _draft = updated);
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
  Widget build(BuildContext context) => Card(
        key: const ValueKey('attendance-insights'),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('出席洞察'),
            Text('可出席 ${insights.attending} 人・不出席 ${insights.unavailable} 人・未回覆 ${insights.unanswered} 人'),
            Text('回覆率 ${insights.responsePercent}%・已回覆者可出席比例 ${insights.availabilityPercent}%'),
            if (insights.isSmallSample) const Text('樣本很少，僅供目前回覆的整理。'),
            Text(insights.callout(offline: offline)),
          ]),
        ),
      );
}

class _LineupLabPage extends StatefulWidget {
  const _LineupLabPage({required this.draft, required this.offline});
  final LineupDraft draft;
  final bool offline;

  @override
  State<_LineupLabPage> createState() => _LineupLabPageState();
}

class _LineupLabPageState extends State<_LineupLabPage> {
  late LineupDraft _draft;

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
            if (widget.offline) const Text('離線快取來源可能過期；草稿仍只存在此畫面。'),
            const SizedBox(height: 12),
            Text('先發／棒次（${_draft.starters.length}）'),
            for (var index = 0; index < _draft.starters.length; index++)
              ListTile(
                key: ValueKey('lineup-starter-${_draft.starters[index].id}'),
                title: Text('${index + 1}. ${_draft.starters[index].displayName}'),
                leading: IconButton(
                  key: ValueKey('lineup-up-${_draft.starters[index].id}'),
                  icon: const Icon(Icons.arrow_upward),
                  onPressed: index == 0 ? null : () => setState(() => _draft.moveStarter(index, index - 1)),
                ),
                trailing: IconButton(
                  key: ValueKey('lineup-bench-${_draft.starters[index].id}'),
                  icon: const Icon(Icons.remove_circle_outline),
                  onPressed: () => setState(() => _draft.moveToBench(_draft.starters[index])),
                ),
              ),
            const Divider(),
            Text('候補（${_draft.bench.length}）'),
            for (final player in _draft.bench)
              ListTile(
                key: ValueKey('lineup-add-${player.id}'),
                title: Text(player.displayName),
                trailing: IconButton(
                  icon: const Icon(Icons.add_circle_outline),
                  onPressed: () => setState(() => _draft.addStarter(player)),
                ),
              ),
            TextButton.icon(
              key: const ValueKey('lineup-reset'),
              onPressed: () => setState(_draft.reset),
              icon: const Icon(Icons.restart_alt),
              label: const Text('重設草稿'),
            ),
          ],
          ),
        ),
      );
}
