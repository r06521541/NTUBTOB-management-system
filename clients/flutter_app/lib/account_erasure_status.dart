import 'package:flutter/material.dart';

/// Strict current POST /api/v1/account-erasure/status response (not a request).
class AccountErasureStatus {
  const AccountErasureStatus._(
      this.id, this.status, this.requestedAt, this.updatedAt);

  final String id;
  final String status;
  final DateTime requestedAt;
  final DateTime updatedAt;

  static const messages = {
    'requested': '申請已記錄，尚待身分驗證；不表示資料已刪除。',
    'verified': '身分驗證已完成，刪除尚未完成。',
    'processing': '正在處理刪除，尚未完成。',
    'needs_attention': '處理需要進一步確認，尚未完成；不必重新提出申請。',
    'online_completed': '本服務的線上資料處理已完成；第三方授權與備份仍須分別確認，尚非整體完成。',
    'completed': '服務回報刪除流程已完成；此狀態不保證收件者或外部平台的副本已移除。',
    'cancelled': '申請已取消；不代表登入權限、憑證或已處理的資料已恢復。',
  };

  static bool validId(Object? value) =>
      value is String &&
      value.length == 36 &&
      RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
          .hasMatch(value);

  static DateTime _time(Object? value) {
    if (value is! String ||
        value.length > 32 ||
        !RegExp(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|\+00:00)$')
            .hasMatch(value)) {
      throw const FormatException('invalid status time');
    }
    final parsed = DateTime.tryParse(value);
    if (parsed == null ||
        !parsed.isUtc ||
        parsed.toIso8601String().substring(0, 19) != value.substring(0, 19)) {
      throw const FormatException('invalid status time');
    }
    return parsed;
  }

  static AccountErasureStatus parse(Map<String, dynamic> value) {
    if (value.length != 4 ||
        !value.keys
            .toSet()
            .containsAll({'id', 'status', 'requested_at', 'updated_at'}) ||
        !validId(value['id']) ||
        value['status'] is! String ||
        !messages.containsKey(value['status'])) {
      throw const FormatException('invalid status envelope');
    }
    final requested = _time(value['requested_at']);
    final updated = _time(value['updated_at']);
    if (updated.isBefore(requested)) {
      throw const FormatException('invalid status order');
    }
    return AccountErasureStatus._(
        value['id'] as String, value['status'] as String, requested, updated);
  }
}

/// Explicit injection only. Implementations own the in-memory receipt and must
/// notify changes when connectivity or receipt ownership/currentness changes.
/// Receipt possession is not a business session, request or cancellation grant.
abstract interface class AccountErasureStatusPort {
  Listenable get changes;
  bool get online;
  String get jobId;
  void requireCurrent();
  Future<Map<String, dynamic>> read();
}

class AccountErasureStatusPage extends StatefulWidget {
  const AccountErasureStatusPage({super.key, required this.reader});
  final AccountErasureStatusPort reader;

  @override
  State<AccountErasureStatusPage> createState() =>
      _AccountErasureStatusPageState();
}

class _AccountErasureStatusPageState extends State<AccountErasureStatusPage> {
  int _epoch = 0;
  bool _loading = false;
  bool _stale = false;
  AccountErasureStatus? _status;
  String _message = '正在查詢處理狀態';

  @override
  void initState() {
    super.initState();
    widget.reader.changes.addListener(_changed);
    _load();
  }

  @override
  void didUpdateWidget(AccountErasureStatusPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.reader, widget.reader)) {
      oldWidget.reader.changes.removeListener(_changed);
      widget.reader.changes.addListener(_changed);
      _stale = false;
      _load();
    }
  }

  @override
  void dispose() {
    _epoch++;
    widget.reader.changes.removeListener(_changed);
    super.dispose();
  }

  bool _current() {
    try {
      widget.reader.requireCurrent();
      return !_stale;
    } on Object {
      _stale = true;
      return false;
    }
  }

  void _changed() {
    _epoch++;
    final current = _current();
    setState(() {
      _loading = false;
      _status = null;
      _message = !current
          ? '查詢憑證已變更，請重新開啟狀態頁。'
          : !widget.reader.online
              ? '目前離線，無法確認最新處理狀態。'
              : '連線或查詢狀態已變更，請手動重新查詢。';
    });
  }

  Future<void> _load() async {
    final epoch = ++_epoch;
    final reader = widget.reader;
    if (!_current() || !reader.online) {
      _changed();
      return;
    }
    setState(() {
      _loading = true;
      _status = null;
      _message = '正在查詢處理狀態';
    });
    try {
      final expected = reader.jobId;
      if (!AccountErasureStatus.validId(expected)) {
        throw const FormatException('invalid receipt context');
      }
      final envelope = await reader.read();
      if (!mounted || epoch != _epoch || !identical(reader, widget.reader)) {
        return;
      }
      if (!_current() || !reader.online) {
        _changed();
        return;
      }
      final result = AccountErasureStatus.parse(envelope);
      if (result.id != expected || reader.jobId != expected) {
        throw const FormatException('receipt context changed');
      }
      setState(() {
        _loading = false;
        _status = result;
        _message = AccountErasureStatus.messages[result.status]!;
      });
    } on Object {
      if (!mounted || epoch != _epoch || !identical(reader, widget.reader)) {
        return;
      }
      if (!_current() || !reader.online) {
        _changed();
        return;
      }
      setState(() {
        _loading = false;
        _status = null;
        _message = '目前無法確認狀態，請稍後手動重新查詢；不會重新提出申請。';
      });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('刪除申請處理狀態')),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          const Text('此頁只查詢服務紀錄，不會提出、驗證或取消申請。'),
          Semantics(liveRegion: true, child: Text(_message)),
          if (_status != null)
            Text('紀錄更新時間：${_status!.updatedAt.toIso8601String()}'),
          TextButton(
              onPressed:
                  _loading || _stale || !widget.reader.online ? null : _load,
              child: const Text('重新查詢')),
        ]),
      );
}
