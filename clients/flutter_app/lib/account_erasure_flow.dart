import 'package:flutter/material.dart';

import 'account_erasure_status.dart';

/// Explicit composition only. No native, transport or credential storage here.
/// Capabilities come from the trusted adapter, not absence of a receipt. Changing
/// owner/context must change generation, invalidate requireCurrent and notify
/// changes before exposing another owner's receipt. Connectivity also notifies.
///
/// Mutations must recheck currentness/online at every asynchronous boundary, use
/// a fresh nonce-bound provider for verify/cancel, validate the committed response
/// and preserve any receipt for recovery. Persist/retain outcomeUnknown before a
/// possibly committing submission; a new page must not reset that uncertainty.
/// readStatus and recoverReceipt must never submit/retry a mutation, authenticate
/// a business session, or create/enumerate another owner's receipt.
abstract interface class AccountErasureFlowPort {
  Listenable get changes;
  bool get online;
  int get generation;
  bool get canRequest;
  bool get outcomeUnknown;
  String? get jobId;
  void requireCurrent();

  /// Null means no receipt in this context, not permission to create an account
  /// or retry an uncertain request. A non-null envelope must match jobId.
  Future<Map<String, dynamic>?> readStatus();
  Future<void> request({required bool confirmed});
  Future<void> verify({required bool confirmed});
  Future<void> cancel({required bool confirmed});

  /// Explicitly reopens an existing receipt for the same authorized owner scope.
  /// No sign-in, enrollment, proof submission or new request is implied.
  Future<void> recoverReceipt({required bool confirmed});
}

/// Separate opt-in capability: fresh provider proof retrieves an existing receipt.
/// It never resets an uncertain mutation or creates a business login/new request.
abstract interface class AccountErasureFreshRecoveryPort {
  bool get canRecoverWithProof;
  Future<void> recoverWithProof({required bool confirmed});
}

enum _Action { request, verify, cancel, recover, freshRecover }

class AccountErasureFlowPage extends StatefulWidget {
  const AccountErasureFlowPage({super.key, required this.port});
  final AccountErasureFlowPort port;

  @override
  State<AccountErasureFlowPage> createState() => _AccountErasureFlowPageState();
}

class _AccountErasureFlowPageState extends State<AccountErasureFlowPage> {
  late int _generation;
  int _epoch = 0;
  bool _busy = false;
  bool _stale = false;
  bool _unknown = false;
  bool _readConfirmed = false;
  AccountErasureStatus? _status;
  String _message = '正在查詢申請狀態';

  static const _cancellable = {
    'requested',
    'verified',
    'processing',
    'needs_attention',
  };
  static const _unknownMessage = '送出結果尚未確認；目前僅能查詢狀態，不會自動或再次送出操作。';

  @override
  void initState() {
    super.initState();
    _generation = widget.port.generation;
    _unknown = widget.port.outcomeUnknown;
    widget.port.changes.addListener(_changed);
    _load();
  }

  @override
  void didUpdateWidget(AccountErasureFlowPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.port, widget.port)) {
      oldWidget.port.changes.removeListener(_changed);
      _epoch++;
      _generation = widget.port.generation;
      _busy = false;
      _stale = false;
      _unknown = widget.port.outcomeUnknown;
      _readConfirmed = false;
      _status = null;
      widget.port.changes.addListener(_changed);
      _load();
    }
  }

  @override
  void dispose() {
    _epoch++;
    widget.port.changes.removeListener(_changed);
    super.dispose();
  }

  bool _current() {
    try {
      widget.port.requireCurrent();
      if (widget.port.generation != _generation) _stale = true;
    } on Object {
      _stale = true;
    }
    return !_stale;
  }

  void _changed() {
    if (!mounted) return;
    _epoch++;
    final current = _current();
    setState(() {
      _busy = false;
      _status = null;
      _readConfirmed = false;
      _unknown = _unknown || widget.port.outcomeUnknown;
      _message = !current
          ? '查詢身分已變更，請返回並重新開啟流程。'
          : !widget.port.online
              ? '目前離線，只能閱讀說明，無法查詢或送出操作。'
              : '連線或收據狀態已變更，請手動查詢最新狀態。';
    });
  }

  bool _accept(int epoch, AccountErasureFlowPort port) {
    if (!mounted || epoch != _epoch || !identical(port, widget.port)) {
      return false;
    }
    if (!_current() || !port.online) {
      _changed();
      return false;
    }
    return true;
  }

  bool _allowed(_Action action, {bool duringDialog = false}) {
    if (action == _Action.freshRecover) {
      final port = widget.port;
      return (!_busy || duringDialog) &&
          !_stale &&
          port.online &&
          _readConfirmed &&
          port.jobId == null &&
          port is AccountErasureFreshRecoveryPort &&
          (port as AccountErasureFreshRecoveryPort).canRecoverWithProof;
    }
    if ((_busy && !duringDialog) ||
        _stale ||
        !widget.port.online ||
        !_readConfirmed ||
        _unknown ||
        widget.port.outcomeUnknown) {
      return false;
    }
    return switch (action) {
      _Action.request =>
        widget.port.canRequest && widget.port.jobId == null && _status == null,
      _Action.verify =>
        _status?.status == 'requested' && _status?.id == widget.port.jobId,
      _Action.cancel => _cancellable.contains(_status?.status) &&
          _status?.id == widget.port.jobId,
      _Action.recover => widget.port.jobId == null && _status == null,
      _Action.freshRecover => false,
    };
  }

  Future<void> _load() async {
    if (_busy) return;
    if (!_current() || !widget.port.online) {
      _changed();
      return;
    }
    final port = widget.port;
    final epoch = ++_epoch;
    final expected = port.jobId;
    setState(() {
      _busy = true;
      _status = null;
      _readConfirmed = false;
      _unknown = _unknown || port.outcomeUnknown;
      _message = '正在查詢申請狀態';
    });
    try {
      if (expected != null && !AccountErasureStatus.validId(expected)) {
        throw const FormatException('invalid receipt context');
      }
      final envelope = await port.readStatus();
      if (!_accept(epoch, port)) return;
      final result =
          envelope == null ? null : AccountErasureStatus.parse(envelope);
      if (port.jobId != expected ||
          (result == null ? expected != null : result.id != expected)) {
        throw const FormatException('receipt context changed');
      }
      setState(() {
        _busy = false;
        _readConfirmed = true;
        _status = result;
        _unknown = _unknown || port.outcomeUnknown;
        _message = result == null
            ? '目前沒有可查詢的收據；這不代表先前的送出一定沒有發生。'
            : AccountErasureStatus.messages[result.status]!;
      });
    } on Object {
      if (!_accept(epoch, port)) return;
      setState(() {
        _busy = false;
        _unknown = _unknown || port.outcomeUnknown;
        _message = '目前無法確認申請狀態，請稍後手動查詢；不會重新送出操作。';
      });
    }
  }

  Future<void> _act(_Action action) async {
    if (!_allowed(action)) return;
    if (!_current()) {
      _changed();
      return;
    }
    final port = widget.port;
    final expected = port.jobId;
    final epoch = ++_epoch;
    setState(() => _busy = true);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(switch (action) {
          _Action.request => '確認提出刪除申請？',
          _Action.verify => '確認驗證這筆刪除申請？',
          _Action.cancel => '確認取消這筆刪除申請？',
          _Action.recover => '重新開啟既存查詢收據？',
          _Action.freshRecover => '驗證身分並取回收據？',
        }),
        content: Text(switch (action) {
          _Action.request => '這會提出目前帳號的刪除意願，仍須驗證與後續處理；帳號與資料尚未刪除。',
          _Action.verify => '將進行新的身分驗證。驗證完成不代表資料已刪除，且一般登入可能失效；請保留查詢收據。',
          _Action.cancel => '不可逆處理開始後，服務將拒絕取消。取消不會恢復登入權限、憑證或已處理的資料。',
          _Action.recover => '僅重新開啟此身分範圍內既存的查詢收據，不會登入、建立帳號或提出新申請。',
          _Action.freshRecover =>
            '將向登入服務重新驗證身分，只取回尚可恢復的原申請收據；不會重新申請、刪除資料或恢復一般登入。帳號已刪除且原收據遺失時可能無法恢復。',
        }),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('返回'),
          ),
          FilledButton(
            key: ValueKey('confirm-erasure-flow-${action.name}'),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('確認繼續'),
          ),
        ],
      ),
    );
    if (!_accept(epoch, port)) return;
    if (confirmed != true) {
      setState(() => _busy = false);
      return;
    }
    if (port.jobId != expected || !_allowed(action, duringDialog: true)) {
      _changed();
      return;
    }
    final mutation =
        action != _Action.recover && action != _Action.freshRecover;
    setState(() {
      // Conservatively latch before the first await, including lost responses.
      _unknown = _unknown || mutation;
      _readConfirmed = false;
      _status = null;
      _message = mutation ? '正在處理操作，請稍候。' : '正在重新開啟查詢收據。';
    });
    try {
      switch (action) {
        case _Action.request:
          await port.request(confirmed: true);
        case _Action.verify:
          await port.verify(confirmed: true);
        case _Action.cancel:
          await port.cancel(confirmed: true);
        case _Action.recover:
          await port.recoverReceipt(confirmed: true);
        case _Action.freshRecover:
          await (port as AccountErasureFreshRecoveryPort)
              .recoverWithProof(confirmed: true);
      }
      if (!_accept(epoch, port)) return;
      if ((action == _Action.request ||
              action == _Action.recover ||
              action == _Action.freshRecover) &&
          !AccountErasureStatus.validId(port.jobId)) {
        throw const FormatException('receipt was not established');
      }
      if (expected != null && port.jobId != expected) {
        _changed();
        return;
      }
      setState(() {
        _busy = false;
        _unknown = port.outcomeUnknown;
        _message = switch (action) {
          _Action.request => '申請已記錄；帳號與資料尚未刪除。請手動查詢最新狀態。',
          _Action.verify => '驗證操作已回覆；不代表資料已刪除。請手動查詢最新狀態。',
          _Action.cancel => '取消操作已回覆；不代表登入或資料已恢復。請手動查詢最新狀態。',
          _Action.recover => '收據查詢已重新開啟，請手動查詢；不會建立新申請。',
          _Action.freshRecover => '已取回原申請收據，請手動查詢狀態；先前結果不明的操作不會重送。',
        };
      });
    } on Object {
      if (!_accept(epoch, port)) return;
      setState(() {
        _busy = false;
        _unknown = _unknown || port.outcomeUnknown;
        _message = mutation ? '無法確認送出結果，請保留收據並查詢狀態。' : '無法重新開啟查詢收據；未因此提出新申請。';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final onlyRead = _stale || _unknown || widget.port.outcomeUnknown;
    return Scaffold(
      appBar: AppBar(title: const Text('帳號刪除流程')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('此功能須由服務明確啟用。提出申請與完成驗證，均不表示帳號或資料已刪除。'),
        const SizedBox(height: 24),
        Semantics(liveRegion: true, child: Text(_message)),
        if ((_unknown || widget.port.outcomeUnknown) && !_stale)
          const Text(_unknownMessage),
        const SizedBox(height: 20),
        if (!onlyRead && widget.port.canRequest && widget.port.jobId == null)
          FilledButton(
            key: const ValueKey('erasure-flow-request'),
            onPressed:
                _allowed(_Action.request) ? () => _act(_Action.request) : null,
            child: const Text('提出刪除申請'),
          ),
        if (!onlyRead && _status?.status == 'requested')
          FilledButton(
            key: const ValueKey('erasure-flow-verify'),
            onPressed:
                _allowed(_Action.verify) ? () => _act(_Action.verify) : null,
            child: const Text('驗證刪除申請'),
          ),
        if (!onlyRead && _cancellable.contains(_status?.status))
          TextButton(
            key: const ValueKey('erasure-flow-cancel'),
            onPressed:
                _allowed(_Action.cancel) ? () => _act(_Action.cancel) : null,
            child: const Text('取消申請'),
          ),
        if (!onlyRead && widget.port.jobId == null)
          TextButton(
            key: const ValueKey('erasure-flow-recover'),
            onPressed:
                _allowed(_Action.recover) ? () => _act(_Action.recover) : null,
            child: const Text('重新開啟既存收據'),
          ),
        if (!_stale &&
            widget.port is AccountErasureFreshRecoveryPort &&
            (widget.port as AccountErasureFreshRecoveryPort)
                .canRecoverWithProof)
          TextButton(
            key: const ValueKey('erasure-flow-freshRecover'),
            onPressed: _allowed(_Action.freshRecover)
                ? () => _act(_Action.freshRecover)
                : null,
            child: const Text('驗證身分取回收據'),
          ),
        TextButton(
          key: const ValueKey('erasure-flow-status'),
          onPressed: _busy || _stale || !widget.port.online ? null : _load,
          child: const Text('查詢最新狀態'),
        ),
      ]),
    );
  }
}
