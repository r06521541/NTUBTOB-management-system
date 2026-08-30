import 'package:flutter/material.dart';

import 'app_theme.dart';

class AppBuildMetadata {
  const AppBuildMetadata({this.version, this.build});

  final String? version;
  final String? build;

  static const fromEnvironment = AppBuildMetadata(
    version: String.fromEnvironment('APP_VERSION'),
    build: String.fromEnvironment('APP_BUILD'),
  );

  String get versionLabel => _label(version);
  String get buildLabel => _label(build);

  static String _label(String? value) {
    final trimmed = value?.trim();
    return trimmed == null || trimmed.isEmpty ? '未提供' : trimmed;
  }
}

class SupportAppInfoPage extends StatelessWidget {
  const SupportAppInfoPage({
    super.key,
    this.metadata = AppBuildMetadata.fromEnvironment,
  });

  final AppBuildMetadata metadata;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('支援與 App 資訊')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const AppPageTitle(
              eyebrow: 'SUPPORT',
              title: '需要協助嗎？',
              subtitle: '了解資料來源、通知限制與目前安裝版本。',
            ),
            const SizedBox(height: 24),
            const _InfoSection(
              key: ValueKey('account-deletion-request'),
              title: '帳號與刪除申請',
              body:
                  '如需更正資料或刪除帳號，請透過既有球隊聯絡管道向管理員提出「帳號刪除申請」，並說明想處理的帳號。管理員會先確認申請人與處理範圍；請不要傳送密碼、登入權杖或其他機密資料。登出 App 不會刪除帳號或伺服器資料。',
            ),
            const _InfoSection(
              title: '資料使用與隱私',
              body:
                  '本 App 會使用帳號識別、賽程、出席回覆與通知內容，提供球隊管理與資訊查閱。App 不會在此頁顯示密碼、權杖或其他機密資料，亦不以廣告為目的使用資料，或將資料出售給第三方。',
            ),
            const _InfoSection(
              title: '通知說明',
              body:
                  '若你在裝置設定中允許通知，通知可用於提醒賽程、出席或隊務資訊；是否允許由你自行決定。本 App 內的通知中心仍可獨立查看通知，本頁不會要求或判斷裝置通知權限。',
            ),
            const Divider(),
            ListTile(
              key: const ValueKey('app-version-metadata'),
              leading: const Icon(Icons.info_outline),
              title: const Text('App 版本'),
              subtitle: Text(metadata.versionLabel),
            ),
            ListTile(
              key: const ValueKey('app-build-metadata'),
              leading: const Icon(Icons.build_outlined),
              title: const Text('Build'),
              subtitle: Text(metadata.buildLabel),
            ),
          ],
        ),
      );
}

class _InfoSection extends StatelessWidget {
  const _InfoSection({super.key, required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) => AppSurfaceCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(body),
          ],
        ),
      );
}
