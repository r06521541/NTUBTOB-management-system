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
    expect(find.text('帳號協助'), findsOneWidget);
    expect(find.text('資料使用與隱私'), findsOneWidget);
    expect(find.text('通知說明'), findsOneWidget);
    expect(find.text('1.2.3'), findsOneWidget);
    expect(find.text('456'), findsOneWidget);
  });
}
