import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/foundation.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/local_preferences.dart';
import 'package:ntubtob_portal/pending_review.dart';
import 'package:ntubtob_portal/production_demo.dart';

class _Transport implements ApiTransport {
  final calls =
      <(String, String, Map<String, String>, Map<String, dynamic>?)>[];
  ApiResponse response =
      const ApiResponse(200, {'status': 'pending', 'messages': []});
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    calls.add((method, path, headers, body));
    return response;
  }
}

class _PermissionPort implements NotificationPermissionPort {
  int requests = 0, settings = 0;
  @override
  Future<void> openSystemSettings() async => settings++;
  @override
  Future<bool> requestPermission() async {
    requests++;
    return false;
  }
}

void main() {
  AppConfig realConfig() => AppConfig.parse(
        flavor: 'staging',
        mode: 'real',
        apiBaseUrl: 'https://example.invalid/api/v1',
        lineChannelId: '1234567890',
        googleClientId: 'fake-ios-client-id',
        googleServerClientId: 'fake-server-client-id',
      );
  test('preferences are installation local and theme never needs a principal',
      () async {
    final store = MemoryStore();
    final first = LocalPreferences(store, 'first');
    final second = LocalPreferences(store, 'second');
    expect(await first.theme(), LocalThemePreference.system);
    await first.saveTheme(LocalThemePreference.dark);
    await first.completeOnboarding();
    expect(await first.theme(), LocalThemePreference.dark);
    expect(await first.onboardingComplete(), isTrue);
    expect(await second.theme(), LocalThemePreference.system);
    expect(await second.onboardingComplete(), isFalse);
  });

  test('permission port has no implicit action and invokes only explicit taps',
      () async {
    final port = _PermissionPort();
    final actions = NotificationPermissionActions(port);
    expect(port.requests, 0);
    expect(port.settings, 0);
    expect(await actions.requestAfterExplicitTap(), isFalse);
    await actions.openSettingsAfterExplicitTap();
    expect(port.requests, 1);
    expect(port.settings, 1);
  });

  test(
      'review credential is purpose separated from sessions and only targets review routes',
      () async {
    final transport = _Transport();
    final client =
        PendingReviewClient(transport, 'review-only-secret', SecureIds());
    await client.read();
    await client.append('請協助確認');
    expect(transport.calls.map((call) => call.$2),
        ['/auth/line/review', '/auth/line/review/messages']);
    for (final call in transport.calls) {
      expect(call.$3['Authorization'], 'Bearer review-only-secret');
    }
    expect(transport.calls.last.$3, contains('Idempotency-Key'));
    client.retire();
    await expectLater(client.read(), throwsA(isA<ContractException>()));
    await expectLater(
      client.append('retired'),
      throwsA(isA<ContractException>()),
    );
  });

  test('profile mutation parses refreshed root person', () {
    final mutation = ProfileMutation.fromJson({
      'person': {
        'id': 'person_1',
        'display_name': '新名稱',
        'access_level': 'basic',
        'capabilities': ['games:read']
      },
      'changed': true,
      'idempotent_replay': false,
    });
    expect(mutation.person.displayName, '新名稱');
    expect(mutation.changed, isTrue);
  });

  testWidgets('onboarding can be skipped and completion is persisted',
      (tester) async {
    final preferences = LocalPreferences(MemoryStore(), 'install');
    await tester.pumpWidget(MaterialApp(
      home: OnboardingPage(onComplete: preferences.completeOnboarding),
    ));
    expect(find.text('歡迎使用隊務系統'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('skip-onboarding')));
    await tester.pump();
    expect(await preferences.onboardingComplete(), isTrue);
  });

  testWidgets(
      'settings render has zero permission side effects and theme applies',
      (tester) async {
    final port = _PermissionPort();
    final preferences = LocalPreferences(MemoryStore(), 'install');
    LocalThemePreference? selected;
    await tester.pumpWidget(MaterialApp(
        home: LocalPreferencesPage(
      preferences: preferences,
      permissions: NotificationPermissionActions(port),
      onThemeChanged: (value) => selected = value,
    )));
    await tester.pump();
    expect(port.requests, 0);
    expect(port.settings, 0);
    await tester.tap(find.byKey(const ValueKey('theme-preference')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('dark').last);
    await tester.pump();
    expect(selected, LocalThemePreference.dark);
    expect(await preferences.theme(), LocalThemePreference.dark);
    await tester
        .tap(find.byKey(const ValueKey('request-notification-permission')));
    await tester.pump();
    expect(port.requests, 1);
  });

  testWidgets('fictional demo reaches shared pending and settings widgets',
      (tester) async {
    await tester.pumpWidget(const ProductionDemoApp(
      flavor: FlavorConfig(AppFlavor.development),
    ));
    await tester.tap(find.byKey(const ValueKey('demo-pending-review')));
    await tester.pumpAndSettle();
    expect(find.byType(PendingReviewPage), findsOneWidget);
    expect(find.text('請補充球隊屆別。'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('demo-settings')));
    await tester.pumpAndSettle();
    expect(find.byType(LocalPreferencesPage), findsOneWidget);
  });

  testWidgets(
      'Basic root gates first run and skip persists without permission I/O',
      (tester) async {
    final store = MemoryStore();
    await store.write('installation:v1', 'install');
    final port = _PermissionPort();
    await tester.pumpWidget(BasicBootstrapApp(
      config: realConfig(),
      store: store,
      permissionPort: port,
    ));
    await tester.pump();
    expect(find.byType(OnboardingPage), findsOneWidget);
    expect(port.requests, 0);
    expect(port.settings, 0);
    await tester.tap(find.byKey(const ValueKey('skip-onboarding')));
    await tester.pump();
    expect(
        await LocalPreferences(store, 'install').onboardingComplete(), isTrue);
  });

  testWidgets('Basic root restores persisted dark theme', (tester) async {
    final store = MemoryStore();
    await store.write('installation:v1', 'install');
    final preferences = LocalPreferences(store, 'install');
    await preferences.completeOnboarding();
    await preferences.saveTheme(LocalThemePreference.dark);
    await tester
        .pumpWidget(BasicBootstrapApp(config: realConfig(), store: store));
    await tester.pump();
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).themeMode,
        ThemeMode.dark);
  });
}
