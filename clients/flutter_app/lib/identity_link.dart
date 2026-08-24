import 'package:flutter/material.dart';
import 'integration.dart';

enum LoginProvider { line, google }

enum IdentityLinkStage {
  idle,
  candidateReady,
  proofReady,
  confirming,
  completed,
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
    await Future.wait([line.logout(), google.logout()]);
  }
}

class IdentityLinkController extends ChangeNotifier {
  IdentityLinkController(
      {required this.transport,
      required this.credentials,
      required this.installationId,
      required this.ids,
      this.session,
      this.onRecovered,
      this.online = true});
  final ApiTransport transport;
  final IdentityCredentialPort credentials;
  final String installationId;
  final SecureIds ids;
  final SessionController? session;
  final Future<void> Function()? onRecovered;
  final bool online;
  IdentityLinkStage stage = IdentityLinkStage.idle;
  String? candidateCredential, proofCredential;
  LoginProvider? candidateProvider, proofProvider;
  Map<String, dynamic>? safeSummary;
  List<LinkedLoginMethod> linkedMethods = const [];
  bool linkedMethodsLoaded = false;

  Future<void> loadLinkedMethods() async {
    if (!online || linkedMethodsLoaded) return;
    try {
      final response = await transport.send('GET', '/auth/identities');
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
      notifyListeners();
    } on Object {
      stage = IdentityLinkStage.error;
      notifyListeners();
    }
  }

  Future<void> begin(LoginProvider provider) async {
    if (!online || stage != IdentityLinkStage.idle) return;
    try {
      final nonce = provider == LoginProvider.line ? ids.next() : null;
      final token = await credentials.authenticate(provider, nonce: nonce);
      if (token == null) {
        stage = IdentityLinkStage.cancelled;
        notifyListeners();
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
      if (response.status != 201 ||
          response.body?['candidate_credential'] is! String) {
        throw const ContractException('invalid candidate');
      }
      candidateCredential = response.body!['candidate_credential'] as String;
      candidateProvider = provider;
      stage = IdentityLinkStage.candidateReady;
      notifyListeners();
    } on Object {
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
    try {
      final nonce = provider == LoginProvider.line ? ids.next() : null;
      final token = await credentials.authenticate(provider, nonce: nonce);
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
    try {
      final response =
          await transport.send('POST', '/auth/identity-link/confirm', body: {
        'candidate_credential': candidateCredential,
        'proof_credential': proofCredential,
        'installation_id': installationId,
        'platform': platform,
        'outcome': recovery ? 'recovery_link' : 'self_link',
        'confirmed': true,
      });
      if (response.status != 200) {
        throw const ContractException('link failed');
      }
      if (recovery && response.body?['session'] != null) {
        final sessionController = session;
        if (sessionController == null || response.body?['session'] is! Map) {
          throw const ContractException('invalid recovery session');
        }
        await sessionController.accept(SessionEnvelope.fromJson(
            Map<String, dynamic>.from(response.body!['session'] as Map)));
        await onRecovered?.call();
      }
      await _retire();
      stage = IdentityLinkStage.completed;
      notifyListeners();
    } on Object {
      stage = IdentityLinkStage.error;
      notifyListeners();
    }
  }

  Future<void> cancel() async {
    if (online) {
      await transport
          .send('POST', '/auth/identity-link/cancel', body: const {});
    }
    await _retire();
    stage = IdentityLinkStage.cancelled;
    notifyListeners();
  }

  Future<void> terminal() async {
    await _retire();
    stage = IdentityLinkStage.idle;
    notifyListeners();
  }

  Future<void> personSwitch() => terminal();

  Future<void> _retire() async {
    candidateCredential = null;
    proofCredential = null;
    candidateProvider = null;
    proofProvider = null;
    safeSummary = null;
    await credentials.clearPresentationState();
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
          if (controller.stage == IdentityLinkStage.idle && controller.online)
            for (final provider in LoginProvider.values)
              if (recovery ||
                  !controller.linkedMethods
                      .any((method) => method.provider == provider.name))
                OutlinedButton(
                    key: ValueKey('identity-link-begin-${provider.name}'),
                    onPressed: () => controller.begin(provider),
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
              controller.stage != IdentityLinkStage.completed)
            TextButton(
                key: const ValueKey('identity-link-cancel'),
                onPressed: controller.cancel,
                child: const Text('取消此裝置上的連結流程')),
        ]),
      );
}

class IdentityRecoveryPage extends StatelessWidget {
  const IdentityRecoveryPage({
    super.key,
    required this.controller,
    required this.platform,
  });
  final IdentityLinkController controller;
  final String platform;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('用其他登入方式追認')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('重新驗證陌生登入方式，再用已連結的另一種登入方式確認帳戶。'),
            IdentityLinkPanel(
              controller: controller,
              platform: platform,
              recovery: true,
            ),
          ],
        ),
      );
}
