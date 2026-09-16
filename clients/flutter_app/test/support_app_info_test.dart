import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/basic_app.dart';
import 'package:ntubtob_portal/integration.dart';
import 'package:ntubtob_portal/local_preferences.dart';
import 'package:ntubtob_portal/support_app_info.dart';

void main() {
  AppConfig realConfig() => AppConfig.parse(
        flavor: 'staging',
        mode: 'real',
        apiBaseUrl: 'https://example.invalid/api/v1',
        lineChannelId: '1234567890',
        googleClientId: 'fixture-ios.apps.googleusercontent.com',
        googleServerClientId: 'fixture-web.apps.googleusercontent.com',
      );

  for (final completedOnboarding in [false, true]) {
    testWidgets(
      'real root exposes local help before login, onboarding=$completedOnboarding',
      (tester) async {
        final store = MemoryStore();
        await store.write('installation:v1', 'install');
        final preferences = LocalPreferences(store, 'install');
        if (completedOnboarding) await preferences.completeOnboarding();
        await tester.pumpWidget(
          BasicBootstrapApp(config: realConfig(), store: store),
        );
        await tester.pumpAndSettle();
        final before = Map<String, String>.of(store.values);
        final authState = completedOnboarding
            ? tester.widget<AuthStatePanel>(find.byType(AuthStatePanel)).state
            : null;

        await tester.tap(find.byTooltip('支援與 App 資訊'));
        await tester.pumpAndSettle();
        expect(find.byType(SupportAppInfoPage), findsOneWidget);
        expect(find.text('帳號與刪除申請'), findsOneWidget);
        expect(store.values, before);

        await tester.pageBack();
        await tester.pumpAndSettle();
        expect(find.byType(SupportAppInfoPage), findsNothing);
        expect(await preferences.onboardingComplete(), completedOnboarding);
        if (completedOnboarding) {
          expect(
            tester.widget<AuthStatePanel>(find.byType(AuthStatePanel)).state,
            authState,
          );
        } else {
          expect(find.byType(OnboardingPage), findsOneWidget);
        }
        expect(store.values, before);
        expect(tester.takeException(), isNull);
      },
    );
  }

  test(
    'build metadata renders missing explicit configuration as unavailable',
    () {
      const metadata = AppBuildMetadata(version: '  ', build: null);

      expect(metadata.versionLabel, '未提供');
      expect(metadata.buildLabel, '未提供');
    },
  );

  testWidgets('support page presents static help and supplied build metadata', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: SupportAppInfoPage(
          metadata: AppBuildMetadata(version: '1.2.3', build: '456'),
        ),
      ),
    );

    expect(find.text('支援與 App 資訊'), findsOneWidget);
    expect(find.text('帳號與刪除申請'), findsOneWidget);
    expect(
        find.byKey(const ValueKey('account-deletion-request')), findsOneWidget);
    expect(find.textContaining('登出 App 不會刪除帳號'), findsOneWidget);
    expect(find.textContaining('既有球隊聯絡管道'), findsOneWidget);
    expect(find.text('資料使用與隱私'), findsOneWidget);
    expect(find.text('通知說明'), findsOneWidget);
    expect(find.textContaining('目前版本不提供裝置推播'), findsOneWidget);
    expect(find.textContaining('不會上傳當機報告'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('app-build-metadata')),
      200,
    );
    expect(find.text('1.2.3'), findsOneWidget);
    expect(find.text('456'), findsOneWidget);
  });
}
