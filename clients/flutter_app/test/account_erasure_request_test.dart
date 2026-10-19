import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/integration.dart';

import 'account_erasure_action_test.dart' as fixture;

class RequestTransport implements ApiTransport {
  final paths = <String>[];
  bool loseResponse = false;
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    expect(headers, isEmpty);
    expect(method, 'POST');
    paths.add(path);
    if (path.endsWith('/challenge')) {
      expect(body, {'provider': 'google'});
      return ApiResponse(200, {
        'provider': 'google',
        'nonce': fixture.nonce,
        'challenge_credential': fixture.credential,
        'expires_in': 300
      });
    }
    expect(path, '/account-erasure/request');
    expect(body, {
      'confirmed': true,
      'provider_assertion': 'fictional-assertion',
      'challenge_credential': fixture.credential
    });
    if (loseResponse) throw StateError('fictional response lost');
    return ApiResponse(202, {
      'id': fixture.job,
      'status': 'requested',
      'receipt_secret': fixture.secret,
      'requested_at': '2035-01-01T00:00:00Z'
    });
  }
}

class FailingReceiptStore extends MemoryStore {
  @override
  Future<void> write(String key, String value) async {
    if (!key.endsWith(':request-attempt')) {
      throw StateError('fictional receipt storage failure');
    }
    await super.write(key, value);
  }
}

void main() {
  test('offline and unconfirmed request never opens provider or transport',
      () async {
    for (final confirmed in [false, true]) {
      final vault =
          ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
      final transport = RequestTransport();
      final provider = fixture.Provider();
      await expectLater(
          ErasureFreshRequestClient(vault, transport,
                  isOnline: () => !confirmed)
              .request(provider: provider, confirmed: confirmed),
          fixture.failure(ErasureActionFailureStage.beforeSubmission));
      expect(transport.paths, isEmpty);
      expect(provider.calls, 0);
      vault.dispose();
    }
  });

  test('receipt storage failure preserves unknown and prevents another request',
      () async {
    final vault =
        ErasureReceiptVault.forTesting(FailingReceiptStore(), fixture.owner);
    final transport = RequestTransport();
    await expectLater(
        ErasureFreshRequestClient(vault, transport, isOnline: () => true)
            .request(provider: fixture.Provider(), confirmed: true),
        fixture.failure(ErasureActionFailureStage.outcomeUnknown));
    expect(await vault.requestWasSubmitted(), isTrue);
    expect(await vault.read(), isNull);
    await expectLater(
        ErasureFreshRequestClient(vault, transport, isOnline: () => true)
            .request(provider: fixture.Provider(), confirmed: true),
        fixture.failure(ErasureActionFailureStage.outcomeUnknown));
    expect(transport.paths.length, 2);
    vault.dispose();
  });

  test('competing request clients share one durable reservation', () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
    final transport = RequestTransport();
    final clients = List.generate(
        2,
        (_) =>
            ErasureFreshRequestClient(vault, transport, isOnline: () => true));
    final results = await Future.wait(clients.map((client) async {
      try {
        await client.request(provider: fixture.Provider(), confirmed: true);
        return true;
      } on ErasureActionFailure {
        return false;
      }
    }));
    expect(results.where((ok) => ok).length, 1);
    expect(
        transport.paths
            .where((path) => path == '/account-erasure/request')
            .length,
        1);
    vault.dispose();
  });
  test('fresh request stores receipt and never creates a business session',
      () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
    final transport = RequestTransport();
    final client =
        ErasureFreshRequestClient(vault, transport, isOnline: () => true);
    await client.request(provider: fixture.Provider(), confirmed: true);
    expect((await vault.read())!.id, fixture.job);
    expect(transport.paths,
        ['/account-erasure/request/challenge', '/account-erasure/request']);
    vault.dispose();
  });

  test('lost request response stays blocked after reopen with no receipt',
      () async {
    final store = MemoryStore();
    var vault = ErasureReceiptVault.forTesting(store, fixture.owner);
    final transport = RequestTransport()..loseResponse = true;
    await expectLater(
        ErasureFreshRequestClient(vault, transport, isOnline: () => true)
            .request(provider: fixture.Provider(), confirmed: true),
        fixture.failure(ErasureActionFailureStage.outcomeUnknown));
    expect(await vault.read(), isNull);
    vault.dispose();
    vault = ErasureReceiptVault.forTesting(store, fixture.owner);
    await expectLater(
        ErasureFreshRequestClient(vault, transport, isOnline: () => true)
            .request(provider: fixture.Provider(), confirmed: true),
        fixture.failure(ErasureActionFailureStage.outcomeUnknown));
    expect(transport.paths.length, 2);
    vault.dispose();
  });

  test('owner change during fresh proof prevents request', () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
    final transport = RequestTransport();
    final provider = fixture.Provider()
      ..result = () async {
        vault.invalidate();
        return 'fictional-assertion';
      };
    await expectLater(
        ErasureFreshRequestClient(vault, transport, isOnline: () => true)
            .request(provider: provider, confirmed: true),
        fixture.failure(ErasureActionFailureStage.beforeSubmission));
    expect(transport.paths.length, 1);
    vault.dispose();
  });
}
