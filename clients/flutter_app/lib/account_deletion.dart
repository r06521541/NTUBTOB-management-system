import 'dart:math';

import 'package:flutter/material.dart';

import 'integration.dart';

class AccountDeletionReceipt {
  const AccountDeletionReceipt(this.id, this.requestedAt);

  final String id;
  final DateTime requestedAt;

  static AccountDeletionReceipt? parse(Map<String, dynamic>? envelope) {
    if (envelope == null ||
        envelope.length != 1 ||
        !envelope.containsKey('request')) {
      throw const ContractException('invalid deletion request envelope');
    }
    final value = envelope['request'];
    if (value == null) return null;
    if (value is! Map<String, dynamic> ||
        value.length != 3 ||
        !value.keys.toSet().containsAll({'id', 'status', 'requested_at'}) ||
        value['status'] != 'requested' ||
        value['id'] is! String ||
        (value['id'] as String).length != 36 ||
        !_uuid.hasMatch(value['id'] as String)) {
      throw const ContractException('invalid deletion request receipt');
    }
    final timestamp = value['requested_at'];
    if (timestamp is! String ||
        timestamp.length > 32 ||
        !RegExp(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$')
            .hasMatch(timestamp)) {
      throw const ContractException('invalid deletion request timestamp');
    }
    final parsed = DateTime.tryParse(timestamp);
    if (parsed == null ||
        !parsed.isUtc ||
        parsed.toIso8601String().substring(0, 19) !=
            timestamp.substring(0, 19)) {
      throw const ContractException('invalid deletion request timestamp');
    }
    return AccountDeletionReceipt(value['id'] as String, parsed);
  }
}

final _uuid = RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
);

String _newRequestId() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  final hex =
      bytes.map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

class AccountDeletionUnavailable implements Exception {
  const AccountDeletionUnavailable();
}

class AccountDeletionOutcomeUncertain implements Exception {
  const AccountDeletionOutcomeUncertain();
}

abstract interface class AccountDeletionPort {
  Listenable? get changes;
  bool get online;
  void requireCurrent();
  Future<AccountDeletionReceipt?> read();
  Future<AccountDeletionReceipt> request({required bool confirmed});
}

/// Explicit injection only. The real application does not compose this client
/// until request intake, fulfillment and policy have a separate rollout review.
class AccountDeletionClient implements AccountDeletionPort {
  AccountDeletionClient(
    this.session, {
    required bool Function() isOnline,
    String Function()? requestId,
  })  : _isOnline = isOnline,
        _requestId = requestId ?? _newRequestId,
        _generation = session.generation;

  final SessionController session;
  final bool Function() _isOnline;
  final String Function() _requestId;
  final int _generation;
  String? _key;

  @override
  Listenable get changes => session.generationChanges;

  @override
  bool get online => _isOnline();

  @override
  void requireCurrent() {
    if (session.generation != _generation) {
      throw const SessionSupersededException();
    }
  }

  void _requireOnline() {
    requireCurrent();
    if (!online) throw const OfflineReadOnlyException();
  }

  @override
  Future<AccountDeletionReceipt?> read() async {
    _requireOnline();
    final response = await session.authorized('GET', '/me/account-deletion');
    requireCurrent();
    if (response.status != 200) throw const AccountDeletionUnavailable();
    return AccountDeletionReceipt.parse(response.body);
  }

  @override
  Future<AccountDeletionReceipt> request({required bool confirmed}) async {
    _requireOnline();
    if (!confirmed) throw ArgumentError('explicit confirmation required');
    final key = _key ??= _requestId();
    if (key.length != 36 || !_uuid.hasMatch(key)) {
      throw const ContractException('invalid deletion request key');
    }
    try {
      final response = await session.authorized(
        'POST',
        '/me/account-deletion',
        headers: {'Idempotency-Key': key},
        body: {'confirmed': true},
      );
      requireCurrent();
      if (response.status != 202) {
        throw const AccountDeletionOutcomeUncertain();
      }
      final receipt = AccountDeletionReceipt.parse(response.body);
      if (receipt == null) throw const AccountDeletionOutcomeUncertain();
      return receipt;
    } on SessionSupersededException {
      rethrow;
    } on SessionExpiredException {
      rethrow;
    } on Object {
      requireCurrent();
      // Even malformed/failed responses cannot prove that POST did not commit.
      throw const AccountDeletionOutcomeUncertain();
    }
  }
}

enum AccountDeletionView {
  loading,
  ready,
  submitting,
  requested,
  uncertain,
  unavailable,
  offline,
  sessionChanged
}

class AccountDeletionPage extends StatefulWidget {
  const AccountDeletionPage({super.key, required this.client});

  final AccountDeletionPort client;

  @override
  State<AccountDeletionPage> createState() => _AccountDeletionPageState();
}

class _AccountDeletionPageState extends State<AccountDeletionPage> {
  AccountDeletionView _view = AccountDeletionView.loading;
  AccountDeletionReceipt? _receipt;
  bool _confirmationOpen = false;
  bool _reconciledEmpty = false;
  bool _submissionUncertain = false;

  @override
  void initState() {
    super.initState();
    widget.client.changes?.addListener(_observeSession);
    _load();
  }

  @override
  void didUpdateWidget(AccountDeletionPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.client, widget.client)) {
      oldWidget.client.changes?.removeListener(_observeSession);
      widget.client.changes?.addListener(_observeSession);
      _receipt = null;
      _reconciledEmpty = false;
      _submissionUncertain = false;
      _load();
    }
  }

  @override
  void dispose() {
    widget.client.changes?.removeListener(_observeSession);
    super.dispose();
  }

  void _observeSession() {
    try {
      widget.client.requireCurrent();
    } on SessionSupersededException {
      _submissionUncertain = false;
      _reconciledEmpty = false;
      _change(AccountDeletionView.sessionChanged);
    }
  }

  void _change(AccountDeletionView view, [AccountDeletionReceipt? receipt]) {
    if (!mounted) return;
    setState(() {
      _view = view;
      _receipt = receipt;
    });
  }

  Future<void> _load() async {
    final client = widget.client;
    _change(AccountDeletionView.loading);
    try {
      final receipt = await client.read();
      if (!mounted || !identical(client, widget.client)) return;
      client.requireCurrent();
      _reconciledEmpty = _submissionUncertain && receipt == null;
      if (receipt != null) _submissionUncertain = false;
      _change(
          receipt == null
              ? AccountDeletionView.ready
              : AccountDeletionView.requested,
          receipt);
    } on Object catch (error) {
      if (!mounted || !identical(client, widget.client)) return;
      _handle(error, submitting: false);
    }
  }

  void _handle(Object error, {required bool submitting}) {
    final view = switch (error) {
      SessionSupersededException() ||
      SessionExpiredException() =>
        AccountDeletionView.sessionChanged,
      OfflineReadOnlyException() => AccountDeletionView.offline,
      _ => submitting
          ? AccountDeletionView.uncertain
          : AccountDeletionView.unavailable,
    };
    if (view == AccountDeletionView.uncertain) _submissionUncertain = true;
    _change(view);
  }

  Future<void> _confirm() async {
    if (_view != AccountDeletionView.ready || _confirmationOpen) return;
    final client = widget.client;
    _confirmationOpen = true;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('確認提出刪除申請？'),
        content:
            const Text('這一步只記錄目前登入帳號的刪除意願，不會立即刪除帳號、隊員或出席紀錄。正式處理範圍與期限尚未啟用。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消')),
          FilledButton(
            key: const ValueKey('confirm-account-deletion-request'),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('確認提出申請'),
          ),
        ],
      ),
    );
    _confirmationOpen = false;
    if (!mounted || !identical(client, widget.client) || confirmed != true) {
      return;
    }
    _change(AccountDeletionView.submitting);
    try {
      client.requireCurrent();
      final receipt = await client.request(confirmed: true);
      if (!mounted || !identical(client, widget.client)) return;
      client.requireCurrent();
      _submissionUncertain = false;
      _change(AccountDeletionView.requested, receipt);
    } on Object catch (error) {
      if (!mounted || !identical(client, widget.client)) return;
      _handle(error, submitting: true);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('帳號刪除申請')),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          const Text('申請流程準備中；正式刪除尚未啟用。此頁不表示帳號或資料已刪除。'),
          const SizedBox(height: 24),
          Semantics(
              liveRegion: true,
              child: Text(switch (_view) {
                AccountDeletionView.loading => '正在查詢申請狀態',
                AccountDeletionView.ready => _reconciledEmpty
                    ? '目前未查到申請，不代表前次送出一定沒有發生。如要再次申請，請重新確認。'
                    : '目前沒有刪除申請',
                AccountDeletionView.submitting => '正在記錄申請，請稍候',
                AccountDeletionView.requested => '申請已記錄；帳號與資料尚未刪除',
                AccountDeletionView.uncertain => '送出結果尚未確認。請查詢狀態；系統不會自動再次送出。',
                AccountDeletionView.unavailable => '目前無法查詢申請狀態，請稍後再查詢。',
                AccountDeletionView.offline => '離線唯讀，無法送出或查詢申請。',
                AccountDeletionView.sessionChanged => '登入狀態已變更，請返回帳號頁重新開啟。',
              })),
          if (_receipt != null) ...[
            const SizedBox(height: 12),
            Text('申請時間：${_receipt!.requestedAt.toUtc().toIso8601String()}'),
          ],
          const SizedBox(height: 20),
          if (_view == AccountDeletionView.ready)
            FilledButton(
              key: const ValueKey('request-account-deletion'),
              onPressed: widget.client.online ? _confirm : null,
              child: const Text('提出刪除申請'),
            ),
          if (_view != AccountDeletionView.loading &&
              _view != AccountDeletionView.submitting &&
              _view != AccountDeletionView.sessionChanged)
            TextButton(
              key: const ValueKey('read-account-deletion-status'),
              onPressed: _load,
              child: const Text('重新查詢狀態'),
            ),
        ]),
      );
}
