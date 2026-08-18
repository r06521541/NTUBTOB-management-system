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

/// Flutter-local display slot for the existing bounded non-responder insight.
/// Thresholds and observation semantics remain server-owned and are not modeled.
class NonResponderInsightUiModel {
  const NonResponderInsightUiModel({required this.summary});

  final String summary;
}

/// Flutter-local single-game report model. It defines no JSON field names.
class SingleGameReportUiModel {
  const SingleGameReportUiModel({
    required this.gameId,
    required this.gameLabel,
    required this.replied,
    required this.notYetReplied,
    this.nonResponderInsight,
  });

  final String gameId;
  final String gameLabel;
  final List<ReportParticipantUiModel> replied;
  final List<ReportParticipantUiModel> notYetReplied;
  final NonResponderInsightUiModel? nonResponderInsight;
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
        replied: [
          ...report.attending.map((person) => ReportParticipantUiModel(
              id: person.personId, displayName: person.displayName)),
          ...report.notAttending.map((person) => ReportParticipantUiModel(
              id: person.personId, displayName: person.displayName)),
        ],
        notYetReplied: report.notYetReplied
            .map((person) => ReportParticipantUiModel(
                id: person.personId, displayName: person.displayName))
            .toList(growable: false),
        nonResponderInsight: report.notYetReplied.isEmpty
            ? null
            : NonResponderInsightUiModel(
                summary: '觀察 ${report.observation.historyGames} 場；'
                    '最低回覆率 ${report.observation.minimumResponseRate}%。'),
      );
    } on NetworkException {
      throw const RetryableOfficerReportException();
    } on SessionExpiredException {
      throw const ExpiredOfficerReportSessionException();
    } on ApiError catch (error) {
      if (error.code == ApiErrorCode.forbidden) {
        throw const ForbiddenOfficerReportException();
      }
      if (error.code == ApiErrorCode.sessionExpired ||
          error.code == ApiErrorCode.unauthenticated) {
        throw const ExpiredOfficerReportSessionException();
      }
      if (error.retryable) throw const RetryableOfficerReportException();
      rethrow;
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

class DeterministicFakeOfficerReportRepository
    implements OfficerReportPresentationPort {
  DeterministicFakeOfficerReportRepository({
    SingleGameReportUiModel? report,
    this.failure,
  }) : report =
            report ?? DeterministicFakeOfficerReportRepository.fictionalReport;

  static const fictionalReport = SingleGameReportUiModel(
    gameId: 'fictional-game',
    gameLabel: '示範賽事',
    replied: [
      ReportParticipantUiModel(id: 'fictional-replied', displayName: '已回覆隊員'),
    ],
    notYetReplied: [
      ReportParticipantUiModel(
        id: 'fictional-not-yet-replied',
        displayName: '尚未回覆隊員',
      ),
    ],
    nonResponderInsight: NonResponderInsightUiModel(summary: '高頻未回覆觀察：示範唯讀資訊'),
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

enum OfficerReportViewState {
  loading,
  empty,
  ready,
  retryableError,
  forbidden,
  sessionExpired,
  offlineCached,
}

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

  String? get principalId => _principalId;
  ManagementPresentationRoute get route => _route;
  RealModePresentationPolicy get policy => RealModePresentationPolicy(_grant);
  bool get mutationsEnabled => false;

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
    notifyListeners();
    if (!online) {
      final cached = await cache.read(principal, gameId);
      report = cached;
      state = cached == null
          ? OfficerReportViewState.retryableError
          : OfficerReportViewState.offlineCached;
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
      state = loaded.replied.isEmpty &&
              loaded.notYetReplied.isEmpty &&
              loaded.nonResponderInsight == null
          ? OfficerReportViewState.empty
          : OfficerReportViewState.ready;
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
    }
    notifyListeners();
  }

  void _revokePresentation() {
    _route = ManagementPresentationRoute.home;
    report = null;
    lastSyncedAt = null;
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
  });

  final BasicApi api;
  final Person person;
  final List<Game> games;
  final bool online;

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
      cache: InMemoryPrincipalOfficerReportCache(),
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
                        ManagementPresentationRoute.singleGameReport
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
  const OfficerReportPanel({super.key, required this.controller});

  final OfficerReportController controller;

  @override
  Widget build(BuildContext context) {
    final semantics = switch (controller.state) {
      OfficerReportViewState.loading => '報表載入中',
      OfficerReportViewState.empty => '此賽事目前沒有回覆資料',
      OfficerReportViewState.ready => '單場出席報表',
      OfficerReportViewState.retryableError => '報表暫時無法載入，請重試',
      OfficerReportViewState.forbidden => '沒有報表讀取權限',
      OfficerReportViewState.sessionExpired => '登入已逾期，報表已關閉',
      OfficerReportViewState.offlineCached => '離線快取唯讀報表',
    };
    return Semantics(
      key: ValueKey('officer-report-${controller.state.name}'),
      label: semantics,
      liveRegion: true,
      child: switch (controller.state) {
        OfficerReportViewState.loading => const Center(
            child: CircularProgressIndicator(),
          ),
        OfficerReportViewState.ready ||
        OfficerReportViewState.offlineCached =>
          _ReportContents(
            report: controller.report!,
            offline: controller.state == OfficerReportViewState.offlineCached,
          ),
        _ => Center(child: Text(semantics)),
      },
    );
  }
}

class _ReportContents extends StatelessWidget {
  const _ReportContents({required this.report, required this.offline});

  final SingleGameReportUiModel report;
  final bool offline;

  @override
  Widget build(BuildContext context) => ListView(
        children: [
          Text(report.gameLabel),
          if (offline) const Text('目前為離線快取，僅供讀取'),
          const Text('已回覆'),
          for (final participant in report.replied)
            Text(participant.displayName),
          const Text('尚未回覆'),
          for (final participant in report.notYetReplied)
            Text(participant.displayName),
          if (report.nonResponderInsight case final insight?) ...[
            const Text('高頻未回覆觀察'),
            Text(insight.summary),
          ],
        ],
      );
}
