import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/integration.dart';
import 'account_erasure_action_test.dart' as fixture;

class RecoveryTransport implements ApiTransport {
  final paths = <String>[];
  void Function()? beforeResult;
  Map<String, dynamic> result = {
    'id': fixture.job,
    'status': 'processing',
    'receipt_secret': fixture.secret,
    'requested_at': '2035-01-01T00:00:00Z',
    'updated_at': '2035-01-02T00:00:00Z',
    'receipt_expires_at': '2035-02-01T00:00:00Z',
  };
  @override
  Future<ApiResponse> send(String method, String path,
      {Map<String, String> headers = const {},
      Map<String, dynamic>? body}) async {
    expect(headers, isEmpty);
    expect(method, 'POST');
    paths.add(path);
    if (path == '/account-erasure/recovery/challenge') {
      expect(body, {'provider': 'google'});
      return ApiResponse(200, {
        'provider': 'google',
        'nonce': fixture.nonce,
        'challenge_credential': fixture.credential,
        'expires_in': 300
      });
    }
    expect(path, '/account-erasure/recovery');
    expect(body, {
      'confirmed': true,
      'provider_assertion': 'fictional-assertion',
      'challenge_credential': fixture.credential
    });
    beforeResult?.call();
    return ApiResponse(200, result);
  }
}

void main() {
  test('competing recovery clients do not overwrite a newly saved receipt',
      () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
    final transport = RecoveryTransport();
    final clients = List.generate(
        2,
        (_) => ErasureFreshRecoveryClient(vault, transport,
            isOnline: () => true, clock: () => DateTime.utc(2035, 1, 3)));
    final outcomes = await Future.wait(clients.map((client) async {
      try {
        await client.recover(provider: fixture.Provider(), confirmed: true);
        return true;
      } on ErasureReceiptUnavailable {
        return false;
      }
    }));
    expect(outcomes.where((value) => value).length, 1);
    expect(vault.revision, 1);
    expect((await vault.read())!.id, fixture.job);
    vault.dispose();
  });

  test('existing receipt blocks recovery before provider or transport',
      () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
    await vault.save(ErasureReceipt.parse({
      'id': fixture.job,
      'status': 'requested',
      'receipt_secret': fixture.secret,
      'requested_at': '2035-01-01T00:00:00Z'
    }));
    final transport = RecoveryTransport();
    final provider = fixture.Provider();
    await expectLater(
        ErasureFreshRecoveryClient(vault, transport, isOnline: () => true)
            .recover(provider: provider, confirmed: true),
        throwsA(isA<ErasureReceiptUnavailable>()));
    expect(transport.paths, isEmpty);
    expect(provider.calls, 0);
    expect((await vault.read())!.id, fixture.job);
    vault.dispose();
  });

  test('offline during provider proof prevents final recovery POST', () async {
    final vault = ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
    final transport = RecoveryTransport();
    var online = true;
    final provider = fixture.Provider()
      ..result = () async {
        online = false;
        return 'fictional-assertion';
      };
    await expectLater(
        ErasureFreshRecoveryClient(vault, transport, isOnline: () => online)
            .recover(provider: provider, confirmed: true),
        throwsA(isA<ErasureReceiptUnavailable>()));
    expect(transport.paths, ['/account-erasure/recovery/challenge']);
    expect(await vault.read(), isNull);
    vault.dispose();
  });
  test('fresh recovery saves original receipt without clearing unknown markers',
      () async {
    final store = MemoryStore();
    await store.write(
        'erasure-receipt:v1:${fixture.owner}:request-attempt', 'unknown');
    final vault = ErasureReceiptVault.forTesting(store, fixture.owner);
    final transport = RecoveryTransport();
    final client = ErasureFreshRecoveryClient(vault, transport,
        isOnline: () => true, clock: () => DateTime.utc(2035, 1, 3));
    await client.recover(provider: fixture.Provider(), confirmed: true);
    final receipt = (await vault.read())!;
    expect(receipt.id, fixture.job);
    expect(receipt.requestedAt, DateTime.utc(2035));
    expect(receipt.expiresAt, DateTime.utc(2035, 2));
    expect(await vault.requestWasSubmitted(), isTrue);
    expect(transport.paths.length, 2);
    await expectLater(
        client.recover(provider: fixture.Provider(), confirmed: true),
        throwsA(isA<ErasureReceiptUnavailable>()));
    expect(transport.paths.length, 2);
    vault.dispose();
  });

  test('offline or unconfirmed never calls provider or transport', () async {
    for (final confirmed in [true, false]) {
      final vault =
          ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
      final transport = RecoveryTransport();
      final provider = fixture.Provider();
      await expectLater(
          ErasureFreshRecoveryClient(vault, transport,
                  isOnline: () => !confirmed)
              .recover(provider: provider, confirmed: confirmed),
          throwsA(isA<ErasureReceiptUnavailable>()));
      expect(provider.calls, 0);
      expect(transport.paths, isEmpty);
      vault.dispose();
    }
  });

  test('expired, malformed or terminal recovery cannot save a receipt',
      () async {
    for (final patch in [
      {'status': 'online_completed'},
      {'status': 'completed'},
      {'receipt_expires_at': '2035-01-01T00:00:00Z'},
      {'updated_at': '2034-01-01T00:00:00Z'},
      {'receipt_expires_at': '2035-02-30T00:00:00Z'},
      {'extra': 'rejected'},
    ]) {
      final vault =
          ErasureReceiptVault.forTesting(MemoryStore(), fixture.owner);
      final transport = RecoveryTransport()..result.addAll(patch);
      await expectLater(
          ErasureFreshRecoveryClient(vault, transport,
                  isOnline: () => true, clock: () => DateTime.utc(2035, 1, 3))
              .recover(provider: fixture.Provider(), confirmed: true),
          throwsA(isA<ErasureReceiptUnavailable>()));
      expect(await vault.read(), isNull);
      expect(await vault.requestWasSubmitted(), isFalse);
      vault.dispose();
    }
  });

  test('owner invalidation or offline result never writes receipt', () async {
    for (final invalidate in [true, false]) {
      final store = MemoryStore();
      final vault = ErasureReceiptVault.forTesting(store, fixture.owner);
      var online = true;
      final transport = RecoveryTransport()
        ..beforeResult = () {
          if (invalidate) {
            vault.invalidate();
          } else {
            online = false;
          }
        };
      await expectLater(
          ErasureFreshRecoveryClient(vault, transport,
                  isOnline: () => online, clock: () => DateTime.utc(2035, 1, 3))
              .recover(provider: fixture.Provider(), confirmed: true),
          throwsA(isA<ErasureReceiptUnavailable>()));
      expect(await store.read('erasure-receipt:v1:${fixture.owner}'), isNull);
      vault.dispose();
    }
  });
}
