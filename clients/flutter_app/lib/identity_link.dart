import 'package:flutter/material.dart';
import 'integration.dart';

enum LoginProvider { line, google }

enum IdentityLinkStage {
  idle,
  candidateReady,
  proofReady,
  confirming,
  completed,
  reauthenticationRequired,
  cancelled,
  error
}

abstract interface class IdentityCredentialPort {
  Future<String?> authenticate(LoginProvider provider, {String? nonce});
  Future<void> clearPresentationState();
}

class NativeIdentityCredentialPort implements IdentityCredentialPort {
  NativeIdentityCredentialPort(this.line, this.google);
  final LineLoginPort line;
  final GoogleLoginPort google;
  @override
  Future<String?> authenticate(LoginProvider provider, {String? nonce}) =>
      provider == LoginProvider.line ? line.login(nonce!) : google.login();
  @override
  Future<void> clearPresentationState() async {
    try {
      await line.logout();
    } on Object {
      // App-session cleanup must not depend on provider presentation state.
    }
    try {
      await google.logout();
    } on Object {
      // Best effort for the second provider as well.
    }
  }
}

class IdentityLinkController extends ChangeNotifier {
  IdentityLinkController(
      {required this.transport,
      required this.credentials,
      required this.installationId,
      required this.ids,
      this.session,
      this.authorizedSend,
      this.onRecovered,
      this.onTerminalSession,
      this.online = true});
  final ApiTransport transport;
  final IdentityCredentialPort credentials;
  final String installationId;
  final SecureIds ids;
  final SessionController? session;
  final Future<ApiResponse> Function(String method, String path,
      {Map<String, dynamic>? body})? authorizedSend;
  final Future<void> Function()? onRecovered;
  final Future<void> Function()? onTerminalSession;
  final bool online;
  IdentityLinkStage stage = IdentityLinkStage.idle;
  String? candidateCredential, proofCredential;
  LoginProvider? candidateProvider, proofProvider;
  Map<String, dynamic>? safeSummary;
  List<LinkedLoginMethod> linkedMethods = const [];
  bool linkedMethodsLoaded = false;
  int _generation = 0;

  Future<void> loadLinkedMethods() async {
    if (!online || linkedMethodsLoaded) return;
    final generation = _generation;
    try {
      final response = await _sendAuthorized('GET', '/auth/identities');
      if (generation != _generation) return;
      final items = response.body?['items'];
      if (response.status != 200 || items is! List) {
        throw const ContractException('invalid identity list');
      }
      linkedMethods = items.map((item) {
        if (item is! Map ||
            item['provider'] is! String ||
            item['label'] is! String ||
            item['linked_at'] is! String) {
          throw const ContractException('invalid identity list item');
        }
        return LinkedLoginMethod(
          provider: item['provider'] as String,
          label: item['label'] as String,
          linkedAt: DateTime.parse(item['linked_at'] as String),
        );
      }).toList(growable: false);
      linkedMethodsLoaded = true;
      if (stage == IdentityLinkStage.error) stage = IdentityLinkStage.idle;
      notifyListeners();
    } on Object catch (error) {
      if (generation != _generation) return;
      if (error is SessionExpiredException) {
        _retireLocal(clearLinkedMethods: true);
        stage = IdentityLinkStage.idle;
        notifyListeners();
        await _clearProviderState();
        await onTerminalSession?.call();
        return;
      }
      linkedMethods = const [];
      linkedMethodsLoaded = false;
      stage = IdentityLinkStage.error;
      notifyListeners();
    }
  }

  Future<void> begin(LoginProvider provider, {bool recovery = false}) async {
    if (!online ||
        stage != IdentityLinkStage.idle ||
        (!recovery && !linkedMethodsLoaded)) {
      return;
    }
    final generation = _generation;
    try {
      final nonce = provider == LoginProvider.line ? ids.next() : null;
      final token = await credentials.authenticate(provider, nonce: nonce);
      if (generation != _generation) return;
      if (token == null) {
        _retireLocal(clearLinkedMethods: false);
        stage = IdentityLinkStage.cancelled;
        notifyListeners();
        await _clearProviderState();
        return;
      }
      final response = await transport.send(
          'POST', '/auth/identity-link/candidates/${provider.name}',
          body: {
            'id_token': token,
            'login_attempt_id': ids.next(),
            'installation_id': installationId,
            if (nonce != null) 'nonce': nonce,
          });
      if (generation != _generation) return;
      if (response.status != 201 ||
          response.body?['candidate_credential'] is! String) {
        throw const ContractException('invalid candidate');
      }
      candidateCredential = response.body!['candidate_credential'] as String;
      candidateProvider = provider;
      stage = IdentityLinkStage.candidateReady;
      notifyListeners();
    } on Object {
      if (generation != _generation) return;
      _retireLocal(clearLinkedMethods: false);
      await _clearProviderState();
      stage = IdentityLinkStage.error;
      notifyListeners();
    }
  }

  Future<void> prove(LoginProvider provider) async {
    if (!online ||
        stage != IdentityLinkStage.candidateReady ||
        provider == candidateProvider) {
      return;
    }
    final generation = _generation;
    try {
      final nonce = provider == LoginProvider.line ? ids.next() : null;
      final token = await credentials.authenticate(provider, nonce: nonce);
      if (generation != _generation) return;
      if (token == null) {
        await cancel();
        return;
      }
      final response = await transport
          .send('POST', '/auth/identity-link/proofs/${provider.name}', body: {
        'candidate_credential': candidateCredential,
        'id_token': token,
        'login_attempt_id': ids.next(),
        'installation_id': installationId,
        if (nonce != null) 'nonce': nonce,
      });
      if (generation != _generation) return;
      if (response.status != 201 ||
          response.body?['proof_credential'] is! String ||
          response.body?['person'] is! Map) {
        throw const ContractException('invalid proof');
      }
      proofCredential = response.body!['proof_credential'] as String;
      proofProvider = provider;
      safeSummary = Map<String, dynamic>.from(response.body!['person'] as Map);
      stage = IdentityLinkStage.proofReady;
      notifyListeners();
    } on Object {
      if (generation != _generation) return;
      _retireLocal(clearLinkedMethods: false);
      await _clearProviderState();
      stage = IdentityLinkStage.error;
      notifyListeners();
    }
  }

  Future<void> confirm(
      {required bool recovery, required String platform}) async {
    if (!online || stage != IdentityLinkStage.proofReady) {
      return;
    }
    stage = IdentityLinkStage.confirming;
    notifyListeners();
    final generation = _generation;
    try {
      final body = <String, dynamic>{
        'candidate_credential': candidateCredential,
        'proof_credential': proofCredential,
        'installation_id': installationId,
        'platform': platform,
        'outcome': recovery ? 'recovery_link' : 'self_link',
        'confirmed': true,
      };
      final response = recovery
          ? await transport.send('POST', '/auth/identity-link/confirm',
              body: body)
          : await _sendAuthorized('POST', '/auth/identity-link/confirm',
              body: body);
      if (generation != _generation) return;
      if (response.status != 200 || response.body is! Map<String, dynamic>) {
        throw const ContractException('link failed');
      }
      final status = response.body!['status'];
      if (recovery && status == 'linked') {
        final sessionController = session;
        if (sessionController == null || response.body?['session'] is! Map) {
          throw const ContractException('invalid recovery session');
        }
        await sessionController.accept(SessionEnvelope.fromJson(
            Map<String, dynamic>.from(response.body!['session'] as Map)));
        await onRecovered?.call();
      } else if (recovery &&
          status == 'already_linked' &&
          response.body?['session'] == null) {
        _retireLocal(clearLinkedMethods: true);
        await _clearProviderState();
        stage = IdentityLinkStage.reauthenticationRequired;
        notifyListeners();
        return;
      } else if (recovery ||
          (status != 'linked' && status != 'already_linked') ||
          response.body?['session'] != null) {
        throw const ContractException('invalid identity-link result');
      }
      _retireLocal(clearLinkedMethods: true);
      await _clearProviderState();
      stage = IdentityLinkStage.completed;
      notifyListeners();
    } on Object catch (error) {
      if (generation != _generation) return;
      if (!recovery && error is SessionExpiredException) {
        _retireLocal(clearLinkedMethods: true);
        stage = IdentityLinkStage.idle;
        notifyListeners();
        await _clearProviderState();
        await onTerminalSession?.call();
        return;
      }
      _retireLocal(clearLinkedMethods: true);
      await _clearProviderState();
      stage = IdentityLinkStage.error;
      notifyListeners();
    }
  }

  Future<void> cancel() async {
    if (!_isActiveFlow) return;
    _retireLocal(clearLinkedMethods: true);
    stage = IdentityLinkStage.cancelled;
    notifyListeners();
    try {
      if (online) {
        await transport
            .send('POST', '/auth/identity-link/cancel', body: const {});
      }
    } on Object {
      // Server proof is bounded and harmless alone; local retirement wins.
    } finally {
      await _clearProviderState();
    }
  }

  Future<void> terminal() async {
    _retireLocal(clearLinkedMethods: true);
    stage = IdentityLinkStage.idle;
    notifyListeners();
    await _clearProviderState();
  }

  Future<void> personSwitch() => terminal();

  void acknowledgeError() {
    if (stage != IdentityLinkStage.error) return;
    stage = IdentityLinkStage.idle;
    notifyListeners();
  }

  Future<void> retrySelfLink() async {
    if (stage != IdentityLinkStage.error) return;
    acknowledgeError();
    await loadLinkedMethods();
  }

  bool get _isActiveFlow => const {
        IdentityLinkStage.candidateReady,
        IdentityLinkStage.proofReady,
        IdentityLinkStage.confirming,
      }.contains(stage);

  void _retireLocal({required bool clearLinkedMethods}) {
    _generation++;
    candidateCredential = null;
    proofCredential = null;
    candidateProvider = null;
    proofProvider = null;
    safeSummary = null;
    if (clearLinkedMethods) {
      linkedMethods = const [];
      linkedMethodsLoaded = false;
    }
  }

  Future<void> _clearProviderState() async {
    try {
      await credentials.clearPresentationState();
    } on Object {
      // Injected ports must not be able to block canonical local retirement.
    }
  }

  Future<ApiResponse> _sendAuthorized(String method, String path,
      {Map<String, dynamic>? body}) {
    final injected = authorizedSend;
    if (injected != null) return injected(method, path, body: body);
    final sessionController = session;
    if (sessionController == null) {
      throw const ContractException('authenticated identity-link unavailable');
    }
    return sessionController.authorized(method, path, body: body);
  }
}

class LinkedLoginMethod {
  const LinkedLoginMethod({
    required this.provider,
    required this.label,
    required this.linkedAt,
  });
  final String provider;
  final String label;
  final DateTime linkedAt;
}

class IdentityLinkPanel extends StatelessWidget {
  const IdentityLinkPanel(
      {super.key,
      required this.controller,
      required this.platform,
      this.recovery = false});
  final IdentityLinkController controller;
  final String platform;
  final bool recovery;
  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) =>
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('新增登入方式', style: TextStyle(fontWeight: FontWeight.bold)),
          if (!recovery)
            for (final method in controller.linkedMethods)
              ListTile(
                key: ValueKey('linked-provider-${method.provider}'),
                contentPadding: EdgeInsets.zero,
                title: Text(method.label),
                subtitle: Text('已連結 ${method.linkedAt.toLocal()}'),
              ),
          if (!controller.online)
            const Text('離線唯讀，無法新增登入方式', key: ValueKey('identity-link-offline')),
          if (!recovery && controller.stage == IdentityLinkStage.error) ...[
            const Text('無法載入登入方式，請重試。', key: ValueKey('identity-link-error')),
            OutlinedButton(
              key: const ValueKey('identity-link-retry'),
              onPressed: controller.retrySelfLink,
              child: const Text('重試'),
            ),
          ],
          if (controller.stage == IdentityLinkStage.idle && controller.online)
            for (final provider in LoginProvider.values)
              if ((recovery || controller.linkedMethodsLoaded) &&
                  (recovery ||
                      !controller.linkedMethods
                          .any((method) => method.provider == provider.name)))
                OutlinedButton(
                    key: ValueKey('identity-link-begin-${provider.name}'),
                    onPressed: () =>
                        controller.begin(provider, recovery: recovery),
                    child: Text(
                        '新增 ${provider == LoginProvider.google ? 'Google' : 'LINE'} 登入')),
          if (controller.stage == IdentityLinkStage.candidateReady)
            for (final provider in LoginProvider.values
                .where((p) => p != controller.candidateProvider))
              ElevatedButton(
                  key: ValueKey('identity-link-proof-${provider.name}'),
                  onPressed: () => controller.prove(provider),
                  child: Text('重新驗證 ${provider.name}')),
          if (controller.stage == IdentityLinkStage.proofReady) ...[
            Text(
                '確認將 ${controller.candidateProvider!.name} 加入 ${controller.safeSummary?['display_name'] ?? '此帳戶'}'),
            ElevatedButton(
                key: const ValueKey('identity-link-confirm'),
                onPressed: () =>
                    controller.confirm(recovery: recovery, platform: platform),
                child: Text(recovery ? '確認追認並登入' : '確認新增登入方式')),
          ],
          if (controller.stage != IdentityLinkStage.idle &&
              const {
                IdentityLinkStage.candidateReady,
                IdentityLinkStage.proofReady,
                IdentityLinkStage.confirming,
              }.contains(controller.stage))
            TextButton(
                key: const ValueKey('identity-link-cancel'),
                onPressed: controller.cancel,
                child: const Text('取消此裝置上的連結流程')),
        ]),
      );
}

class IdentityRecoveryPage extends StatefulWidget {
  const IdentityRecoveryPage({
    super.key,
    required this.controller,
    required this.platform,
  });
  final IdentityLinkController controller;
  final String platform;

  @override
  State<IdentityRecoveryPage> createState() => _IdentityRecoveryPageState();
}

class _IdentityRecoveryPageState extends State<IdentityRecoveryPage> {
  bool _started = false;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onChanged);
  }

  void _onChanged() {
    final stage = widget.controller.stage;
    if (stage != IdentityLinkStage.idle) _started = true;
    if (_started &&
        const {
          IdentityLinkStage.idle,
          IdentityLinkStage.completed,
          IdentityLinkStage.reauthenticationRequired,
          IdentityLinkStage.cancelled,
          IdentityLinkStage.error,
        }.contains(stage)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && Navigator.of(context).canPop()) {
          _started = false;
          Navigator.of(context).pop(stage);
          if (stage == IdentityLinkStage.error) {
            widget.controller.acknowledgeError();
          }
        }
      });
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChanged);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('用其他登入方式追認')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('重新驗證陌生登入方式，再用已連結的另一種登入方式確認帳戶。'),
            IdentityLinkPanel(
              controller: widget.controller,
              platform: widget.platform,
              recovery: true,
            ),
          ],
        ),
      );
}
