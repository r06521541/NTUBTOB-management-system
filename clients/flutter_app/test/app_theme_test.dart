import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/app_theme.dart';

void main() {
  test('light tokens faithfully carry the Web Portal palette', () {
    final theme = appTheme(Brightness.light);
    final tokens = theme.extension<AppVisualTokens>()!;

    expect(theme.colorScheme.primary, appBrandNavy);
    expect(tokens.accent, appBrandGold);
    expect(tokens.canvas, const Color(0xfff5f6f8));
    expect(tokens.surface, const Color(0xffffffff));
    expect(tokens.text, const Color(0xff18212b));
    expect(tokens.muted, const Color(0xff66717e));
    expect(tokens.border, const Color(0xffd9dee5));
    expect(tokens.success, const Color(0xff26734d));
    expect(tokens.warning, const Color(0xff8a641f));
    expect(tokens.danger, const Color(0xffa63d3d));
  });

  test('dark tokens are a readable derivation rather than light constants', () {
    final light = appTheme(Brightness.light).extension<AppVisualTokens>()!;
    final dark = appTheme(Brightness.dark).extension<AppVisualTokens>()!;

    expect(dark.canvas, isNot(light.canvas));
    expect(dark.surface, isNot(light.surface));
    expect(dark.text.computeLuminance(),
        greaterThan(dark.canvas.computeLuminance()));
    expect(dark.success, isNot(light.success));
    expect(dark.warning, isNot(light.warning));
    expect(dark.danger, isNot(light.danger));
  });

  testWidgets('shared components preserve semantics and minimum action target',
      (tester) async {
    var tapped = false;
    await tester.pumpWidget(MaterialApp(
      theme: appTheme(Brightness.light),
      home: Scaffold(
        body: ListView(children: [
          const AppPageTitle(eyebrow: 'NEXT GAME', title: '最近賽事'),
          const AppStatusBadge(
            label: '已確認',
            tone: AppStatusTone.success,
          ),
          const AppNoticePanel(title: '離線', message: '資料唯讀且可能過期'),
          AppSurfaceCard(
            semanticLabel: '開啟賽事',
            onTap: () => tapped = true,
            child: const Text('賽事卡'),
          ),
        ]),
      ),
    ));

    expect(tester.getSemantics(find.text('最近賽事')).flagsCollection.isHeader,
        isTrue);
    expect(tester.getSemantics(find.byType(AppStatusBadge)).label, '已確認');
    expect(
        tester.getSemantics(find.byType(AppNoticePanel)).label, '離線，資料唯讀且可能過期');
    final action = tester.getSemantics(find.bySemanticsLabel('開啟賽事'));
    expect(action.flagsCollection.isButton, isTrue);
    expect(tester.getSize(find.bySemanticsLabel('開啟賽事')).height,
        greaterThanOrEqualTo(44));
    await tester.tap(find.bySemanticsLabel('開啟賽事'));
    expect(tapped, isTrue);
  });

  testWidgets('shared components remain usable with large text scale',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: appTheme(Brightness.dark),
      home: const MediaQuery(
        data: MediaQueryData(textScaler: TextScaler.linear(2)),
        child: Scaffold(
          body: SingleChildScrollView(
            child: AppNoticePanel(
              title: '重要提醒',
              message: '這段內容必須在放大文字時完整閱讀。',
            ),
          ),
        ),
      ),
    ));
    expect(tester.takeException(), isNull);
    expect(find.text('這段內容必須在放大文字時完整閱讀。'), findsOneWidget);
  });
}
