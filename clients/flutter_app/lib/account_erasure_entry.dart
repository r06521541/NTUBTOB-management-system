import 'package:flutter/material.dart';

import 'account_erasure_flow.dart';
import 'account_erasure_owner.dart';
import 'integration.dart';

/// Explicit source composition only; never loaded from environment or main.
/// The trusted factory may replace ports for tests, but receives the actual root
/// session/transport/store. Neither construction nor opening this page starts a
/// provider, business login, request, or persisted scope.
class AccountErasureEntryOptions {
  const AccountErasureEntryOptions({
    required this.isOnline,
    required this.connectivity,
    this.ownerFactory,
  });

  final bool Function() isOnline;
  final Listenable connectivity;
  final AccountErasureOwner Function(AccountErasureRootContext)? ownerFactory;
}

/// Captured once when the entry is tapped, not when its route rebuilds. Its
/// guard expires on root replacement, composition change or session generation
/// change. An opened owner manages its separate receipt lifetime thereafter.
class AccountErasureRootContext {
  const AccountErasureRootContext({
    required this.store,
    required this.session,
    required this.transport,
    required this.line,
    required this.apple,
    required this.options,
    required this.requireCurrent,
  });

  final DurableStore store;
  final SessionController session;
  final ApiTransport transport;
  final LineLoginPort line;
  final AppleLoginPort? apple;
  final AccountErasureEntryOptions options;
  final VoidCallback requireCurrent;
  bool Function() get isOnline => options.isOnline;
  Listenable get connectivity => options.connectivity;

  AccountErasureOwner createOwner() {
    requireCurrent();
    return AccountErasureOwner(
      store: store,
      session: session,
      transport: transport,
      isOnline: isOnline,
      connectivity: connectivity,
      apple: apple,
      line: line,
    );
  }
}

class AccountErasureEntryPage extends StatefulWidget {
  const AccountErasureEntryPage({
    super.key,
    required this.rootContext,
    required this.open,
  });

  final AccountErasureRootContext rootContext;
  final Future<AccountErasureFlowPort> Function(
      {String? provider, required bool resume}) open;

  @override
  State<AccountErasureEntryPage> createState() =>
      _AccountErasureEntryPageState();
}

class _AccountErasureEntryPageState extends State<AccountErasureEntryPage> {
  bool _busy = false;
  bool _unavailable = false;

  Future<void> _open(String action) async {
    if (_busy) {
      return;
    }
    setState(() => _busy = true);
    try {
      widget.rootContext.requireCurrent();
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(action == 'resume' ? '重開既有申請' : '開啟帳號刪除流程'),
          content: Text(action == 'resume'
              ? '這只會重開此裝置既有收據，不會建立新申請或登入帳號。重新啟動後請先登出一般帳號。'
              : '將以所選登入方式進行後續本人驗證。現在只建立此裝置的處理入口；尚未送出刪除申請，也不會刪除資料。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('返回'),
            ),
            FilledButton(
              key: ValueKey('confirm-erasure-entry-$action'),
              onPressed: () => Navigator.pop(context, true),
              child: const Text('確認開啟'),
            ),
          ],
        ),
      );
      if (!mounted || confirmed != true) {
        return;
      }
      widget.rootContext.requireCurrent();
      final flow = await widget.open(
          provider: action == 'resume' ? null : action,
          resume: action == 'resume');
      if (!mounted) {
        return;
      }
      widget.rootContext.requireCurrent();
      flow.requireCurrent();
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
        builder: (_) => AccountErasureFlowPage(port: flow),
      ));
    } on Object {
      // No native error, persisted scope, receipt or token is projected here.
      if (mounted) {
        setState(() => _unavailable = true);
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('帳號刪除入口')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('選擇要驗證的登入方式，或重開此裝置的既有收據。此入口不會自動登入或送出申請。'),
            if (_unavailable) const Text('目前無法開啟；請返回並確認登入狀態。既有收據不會被覆寫。'),
            if (widget.rootContext.apple != null)
              FilledButton(
                key: const ValueKey('erasure-entry-apple'),
                onPressed: _busy ? null : () => _open('apple'),
                child: const Text('使用 Apple 驗證'),
              ),
            FilledButton(
              key: const ValueKey('erasure-entry-line'),
              onPressed: _busy ? null : () => _open('line'),
              child: const Text('使用 LINE 驗證'),
            ),
            OutlinedButton(
              key: const ValueKey('erasure-entry-resume'),
              onPressed: _busy ? null : () => _open('resume'),
              child: const Text('重開既有收據'),
            ),
          ],
        ),
      );
}
