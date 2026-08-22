import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/integration.dart';

class _NoTransport implements ApiTransport {
  int calls = 0;

  @override
  Future<ApiResponse> send(
    String method,
    String path, {
    Map<String, String> headers = const {},
    Map<String, dynamic>? body,
  }) async {
    calls++;
    throw StateError('schedule presentation must not use transport');
  }
}

void main() {
  List<Game> games() => [
        Game(
          'sep-30',
          DateTime.utc(2026, 9, 30, 6),
          90,
          '九月球場',
          '九月隊',
          '校友隊',
        ),
        Game(
          'oct-3-a',
          DateTime.utc(2026, 10, 3, 5),
          120,
          null,
          '猛虎隊',
          '校友隊',
        ),
        Game(
          'oct-3-b',
          DateTime.utc(2026, 10, 3, 8),
          90,
          '十月球場',
          '海豚隊',
          '校友隊',
        ),
        Game(
          'oct-5',
          DateTime.utc(2026, 10, 5, 6),
          120,
          '週界球場',
          '星期一隊',
          '校友隊',
        ),
        Game(
          'jan-1',
          DateTime.utc(2027, 1, 1, 6),
          120,
          '跨年球場',
          '新年隊',
          '校友隊',
        ),
      ];

  test('calendar projection handles month year and Monday week boundaries', () {
    final december = ScheduleCalendarProjection.monthGrid(DateTime(2026, 12));
    expect(december, hasLength(42));
    expect(december.first.weekday, DateTime.monday);
    expect(december.any((day) => day.year == 2027 && day.month == 1), isTrue);

    final week = ScheduleCalendarProjection.weekDays(DateTime(2026, 10, 3));
    expect(week.first, DateTime(2026, 9, 28));
    expect(week.last, DateTime(2026, 10, 4));
    expect(ScheduleCalendarProjection.weekStart(DateTime(2027, 1, 1)),
        DateTime(2026, 12, 28));
  });

  test('calendar grouping keeps multiple local games on the same day', () {
    final groups = ScheduleCalendarProjection.groupByLocalDay(games());
    expect(groups[DateTime(2026, 10, 3)], hasLength(2));
    expect(groups[DateTime(2026, 10, 3)]!.map((game) => game.id),
        ['oct-3-a', 'oct-3-b']);
    expect(groups[DateTime(2027, 1, 1)]!.single.id, 'jan-1');

    final withLocation = ScheduleCalendarProjection.groupByLocalDay(
      games().where((game) => game.location?.isNotEmpty ?? false),
    );
    expect(withLocation[DateTime(2026, 10, 3)], hasLength(1));
    expect(withLocation[DateTime(2026, 10, 3)]!.single.id, 'oct-3-b');
  });

  Future<({BasicApi api, _NoTransport transport})> fakeApi() async {
    final transport = _NoTransport();
    final store = MemoryStore();
    return (
      api: BasicApi(
        SessionController(transport, store, 'schedule-test', SecureIds()),
        store,
        'schedule-test',
        SecureIds(),
      ),
      transport: transport,
    );
  }

  Future<({BasicApi api, _NoTransport transport})> pumpSchedule(
    WidgetTester tester, {
    bool online = true,
    List<Game>? values,
  }) async {
    tester.view.physicalSize = const Size(1600, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final fixture = await fakeApi();
    await tester.pumpWidget(MaterialApp(
      home: ScheduleDiscoveryPage(
        api: fixture.api,
        games: values ?? games(),
        online: online,
      ),
    ));
    await tester.pumpAndSettle();
    return fixture;
  }

  testWidgets('Month Week Agenda share search and location filters',
      (tester) async {
    await pumpSchedule(tester);

    await tester.tap(find.text('月'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('schedule-month-grid')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('schedule-day-2026-10-03')));
    await tester.pumpAndSettle();
    final selectedDay = tester.widget<TextButton>(
      find.byKey(const ValueKey('schedule-day-2026-10-03')),
    );
    final selectedContext = tester.element(
      find.byKey(const ValueKey('schedule-day-2026-10-03')),
    );
    expect(
      selectedDay.style!.backgroundColor!.resolve({}),
      Theme.of(selectedContext).colorScheme.secondaryContainer,
    );
    expect(selectedDay.style!.side!.resolve({})!.width, 2);
    expect(find.byKey(const ValueKey('schedule-game-oct-3-a')), findsOneWidget);
    expect(find.byKey(const ValueKey('schedule-game-oct-3-b')), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('schedule-filter-withLocation')),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('schedule-game-oct-3-a')), findsNothing);
    expect(find.byKey(const ValueKey('schedule-game-oct-3-b')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('schedule-filter-all')));
    await tester.enterText(find.byKey(const ValueKey('schedule-search')), '猛虎');
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('schedule-game-oct-3-a')), findsOneWidget);
    expect(find.byKey(const ValueKey('schedule-game-oct-3-b')), findsNothing);

    await tester.tap(find.text('週'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('schedule-date-2026-09-28T00:00:00.000')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('schedule-game-oct-3-a')), findsOneWidget);

    await tester.tap(find.text('列表'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('schedule-game-oct-3-a')), findsOneWidget);
    expect(find.byKey(const ValueKey('schedule-game-oct-5')), findsNothing);
  });

  testWidgets('selected day distinguishes no game from active-filter no match',
      (tester) async {
    await pumpSchedule(tester);
    await tester.tap(find.text('月'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('schedule-day-2026-10-04')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('schedule-day-no-games')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('schedule-day-2026-10-03')));
    await tester.enterText(
      find.byKey(const ValueKey('schedule-search')),
      '不存在',
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('schedule-day-no-match')), findsOneWidget);
    expect(find.byKey(const ValueKey('schedule-day-no-games')), findsNothing);

    await tester.tap(find.text('週'));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('schedule-week-2026-09-28-no-games')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('schedule-week-2026-10-03-no-match')),
      findsOneWidget,
    );
  });

  testWidgets('period controls Today and detail return retain calendar state',
      (tester) async {
    final fixture = await pumpSchedule(tester, online: false);
    await tester.tap(find.text('月'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('schedule-next-period')));
    await tester.pumpAndSettle();
    expect(find.text('2026 年 10 月'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('schedule-day-2026-10-03')));
    await tester.enterText(find.byKey(const ValueKey('schedule-search')), '海豚');
    await tester.pumpAndSettle();
    await tester.drag(
      find.byType(ListView).first,
      const Offset(0, -900),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('schedule-game-oct-3-b')));
    await tester.pumpAndSettle();
    expect(find.byType(CachedGameDetailPage), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('schedule-month-grid')), findsOneWidget);
    expect(find.text('2026 年 10 月'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byKey(const ValueKey('schedule-search')))
          .controller!
          .text,
      '海豚',
    );

    await tester.tap(find.byKey(const ValueKey('schedule-today')));
    await tester.pumpAndSettle();
    final now = DateTime.now();
    final todayKey = ValueKey(
      'schedule-day-${now.year.toString().padLeft(4, '0')}-'
      '${now.month.toString().padLeft(2, '0')}-'
      '${now.day.toString().padLeft(2, '0')}',
    );
    expect(find.byKey(todayKey), findsOneWidget);
    expect(fixture.transport.calls, 0);
  });
}
