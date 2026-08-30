import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/support_app_info.dart';

void main() {
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
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('app-build-metadata')),
      200,
    );
    expect(find.text('1.2.3'), findsOneWidget);
    expect(find.text('456'), findsOneWidget);
  });
}
