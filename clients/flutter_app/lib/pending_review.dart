import 'package:flutter/material.dart';

import 'integration.dart';

class PendingReviewMessage {
  const PendingReviewMessage(
      this.id, this.sender, this.body, this.createdAt, this.redacted);
  factory PendingReviewMessage.fromJson(Map<String, dynamic> json) =>
      PendingReviewMessage(
        _string(json, 'id'),
        _string(json, 'sender'),
        _string(json, 'body'),
        DateTime.parse(_string(json, 'created_at')).toUtc(),
        json['redacted'] == true,
      );
  final String id, sender, body;
  final DateTime createdAt;
  final bool redacted;
}

class PendingReview {
  const PendingReview(this.messages);
  factory PendingReview.fromJson(Map<String, dynamic> json) {
    if (json['status'] != 'pending' || json['messages'] is! List) {
      throw const ContractException('invalid pending review');
    }
    return PendingReview((json['messages'] as List)
        .map((e) => PendingReviewMessage.fromJson(e as Map<String, dynamic>))
        .toList(growable: false));
  }
  final List<PendingReviewMessage> messages;
}

String _string(Map<String, dynamic> value, String key) {
  final item = value[key];
  if (item is! String || item.isEmpty) {
    throw const ContractException('invalid pending review field');
  }
  return item;
}

/// Deliberately independent of [SessionController]. A review credential cannot
/// populate access/refresh storage or call any authenticated API surface.
class PendingReviewClient {
  PendingReviewClient(this.transport, this.credential, this.ids);
  final ApiTransport transport;
  final String credential;
  final SecureIds ids;
  String? _pendingBody;
  String? _pendingKey;
  bool _active = true;
  Map<String, String> get _headers => {'Authorization': 'Bearer $credential'};

  Future<PendingReview> read() async {
    _ensureActive();
    final response =
        await transport.send('GET', '/auth/line/review', headers: _headers);
    _ensureActive();
    if (response.status != 200 || response.body == null) {
      throw const ContractException('pending review unavailable');
    }
    return PendingReview.fromJson(response.body!);
  }

  Future<PendingReview> append(String body) async {
    _ensureActive();
    final normalized = body.trim();
    if (normalized.isEmpty || normalized.length > 1000) {
      throw const ContractException('invalid pending review message');
    }
    if (_pendingBody != null && _pendingBody != normalized) {
      throw const ContractException('pending review message unresolved');
    }
    final key = _pendingKey ?? ids.next();
    _pendingBody = normalized;
    _pendingKey = key;
    final response = await transport.send('POST', '/auth/line/review/messages',
        headers: {..._headers, 'Idempotency-Key': key},
        body: {'body': normalized});
    _ensureActive();
    if (response.status != 200 || response.body == null) {
      throw const ContractException('pending review message unavailable');
    }
    final review = PendingReview.fromJson(response.body!);
    _pendingBody = null;
    _pendingKey = null;
    return review;
  }

  void retire() {
    _active = false;
    _pendingBody = null;
    _pendingKey = null;
  }

  void _ensureActive() {
    if (!_active) throw const ContractException('pending review retired');
  }
}

class PendingReviewPage extends StatefulWidget {
  const PendingReviewPage({super.key, required this.client});
  final PendingReviewClient client;
  @override
  State<PendingReviewPage> createState() => _PendingReviewPageState();
}

class _PendingReviewPageState extends State<PendingReviewPage> {
  final _body = TextEditingController();
  PendingReview? _review;
  String? _message;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _body.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _busy = true);
    try {
      final review = await widget.client.read();
      if (mounted) {
        setState(() => _review = review);
      }
    } on Object {
      if (mounted) setState(() => _message = '目前無法取得審核狀態；請稍後重新以 LINE 登入。');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _append() async {
    if (_busy || _body.text.trim().isEmpty) return;
    setState(() => _busy = true);
    try {
      final review = await widget.client.append(_body.text);
      if (mounted) {
        setState(() {
          _review = review;
          _body.clear();
        });
      }
    } on Object {
      if (mounted) setState(() => _message = '訊息尚未送出，請稍後重試。');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('LINE 身分審核')),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          const Text('審核期間只能查看此申請與留言；完成後請重新以 LINE 一般登入。'),
          if (_busy && _review == null) const CircularProgressIndicator(),
          for (final item
              in _review?.messages ?? const <PendingReviewMessage>[])
            ListTile(
                title: Text(item.sender == 'applicant' ? '您' : '管理員'),
                subtitle: Text(item.redacted ? '此訊息已遮蔽' : item.body)),
          if (_message != null) Text(_message!),
          TextField(
              controller: _body,
              maxLength: 1000,
              decoration: const InputDecoration(labelText: '補充說明')),
          FilledButton(
              onPressed: _busy ? null : _append, child: const Text('送出留言')),
        ]),
      );
}
