import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_portal/account_erasure_client.dart';
import 'package:ntubtob_portal/account_erasure_provider.dart';
import 'package:ntubtob_portal/integration.dart';

class ProofPorts implements AppleLoginPort, LineLoginPort {
  final nonces = <String>[];
  int logoutCalls = 0;
  int envelopeCalls = 0;
  Future<String> Function() result = () async => 'fictional-proof';

  @override
  Future<String> login(String nonce) {
    nonces.add(nonce);
    return result();
  }

  @override
  Future<void> logout() async {
    logoutCalls++;
  }

  @override
  Future<AppleAuthorizationEnvelope> authorize(String nonce) async {
    envelopeCalls++;
    throw StateError('no enrollment envelope requested');
  }
}

class GoogleProofPort implements GoogleFreshAuthorizationPort {
  GoogleProofPort(this.ports);
  final ProofPorts ports;

  @override
  Future<String> authorize(String nonce,
      {required void Function() beforePrompt}) {
    beforePrompt();
    return ports.login(nonce);
  }
}

void main() {
  final nonce = 'n' * 43;
  final rejected = throwsA(isA<ErasureFreshProviderUnavailable>());
  for (final name in ['apple', 'google', 'line']) {
    group(name, () {
      late ProofPorts ports;
      late ErasureFreshProvider provider;
      late bool current;
      late bool online;
      Future<void> Function()? refresh;
      setUp(() {
        ports = ProofPorts();
        current = true;
        online = true;
        refresh = null;
        void requireCurrent() {
          if (!current) {
            throw StateError('fictional private native detail');
          }
        }

        provider = switch (name) {
          'apple' => AppleErasureFreshProvider(ports,
              requireCurrent: requireCurrent,
              isOnline: () => online,
              afterAuthorization: () async {
                await refresh?.call();
              }),
          'google' => GoogleErasureFreshProvider(GoogleProofPort(ports),
              requireCurrent: requireCurrent,
              isOnline: () => online,
              afterAuthorization: () async {
                await refresh?.call();
              }),
          _ => LineErasureFreshProvider(ports,
              requireCurrent: requireCurrent,
              isOnline: () => online,
              afterAuthorization: () async {
                await refresh?.call();
              }),
        };
      });

      test('native return awaits reachability once without another prompt',
          () async {
        final checked = Completer<void>();
        final entered = Completer<void>();
        ports.result = () async {
          online = false;
          return 'fictional-proof';
        };
        refresh = () async {
          entered.complete();
          await checked.future;
          online = true;
        };
        final pending = provider.authenticate(nonce);
        await entered.future;
        expect(ports.nonces.length, 1);
        expect(online, isFalse);
        checked.complete();
        expect(await pending, 'fictional-proof');
        expect(ports.nonces.length, 1);
        expect(ports.logoutCalls, 0);
      });

      test('stale native return does not even refresh', () async {
        var checks = 0;
        ports.result = () async {
          current = false;
          return 'fictional-proof';
        };
        refresh = () async {
          checks++;
        };
        await expectLater(provider.authenticate(nonce), rejected);
        expect(checks, 0);
      });

      test('stale during refresh or failed probe cannot accept assertion',
          () async {
        refresh = () async {
          current = false;
          online = true;
        };
        await expectLater(provider.authenticate(nonce), rejected);
        current = true;
        refresh = () async {
          online = false;
        };
        await expectLater(provider.authenticate(nonce), rejected);
        expect(ports.logoutCalls, 0);
      });

      test('forwards fresh nonce without logout or enrollment envelope',
          () async {
        expect(provider.provider, name);
        expect(await provider.authenticate(nonce), 'fictional-proof');
        expect(await provider.authenticate('b' * 43), 'fictional-proof');
        expect(ports.nonces, [nonce, 'b' * 43]);
        expect(ports.logoutCalls, 0);
        expect(ports.envelopeCalls, 0);
      });

      test('invalid nonce never reaches native port', () async {
        for (final value in [
          '',
          'n' * 42,
          'n' * 44,
          '${'n' * 42}\n',
          '${'n' * 42}!',
          '${'n' * 42}é'
        ]) {
          await expectLater(provider.authenticate(value), rejected);
        }
        expect(ports.nonces, isEmpty);
      });

      test('stale or offline before authorization makes zero calls', () async {
        current = false;
        await expectLater(provider.authenticate(nonce), rejected);
        current = true;
        online = false;
        await expectLater(provider.authenticate(nonce), rejected);
        expect(ports.nonces, isEmpty);
      });

      for (final stale in [true, false]) {
        test('rejects ${stale ? 'stale' : 'offline'} native completion',
            () async {
          final result = Completer<String>();
          ports.result = () => result.future;
          final pending = provider.authenticate(nonce);
          final checked = expectLater(pending, rejected);
          if (stale) {
            current = false;
          } else {
            online = false;
          }
          result.complete('fictional-proof');
          await checked;
          expect(ports.nonces, [nonce]);
        });
      }

      test('concurrent authorization cannot open a second native prompt',
          () async {
        final result = Completer<String>();
        ports.result = () => result.future;
        final pending = provider.authenticate(nonce);
        await expectLater(provider.authenticate(nonce), rejected);
        result.complete('fictional-proof');
        expect(await pending, 'fictional-proof');
        expect(ports.nonces.length, 1);
      });

      test('invalid assertions and native errors use a fixed safe failure',
          () async {
        for (final value in ['', 'x' * 16385]) {
          ports.result = () async => value;
          await expectLater(provider.authenticate(nonce), rejected);
        }
        ports.result = () async => throw StateError('fictional private detail');
        try {
          await provider.authenticate(nonce);
          fail('expected failure');
        } on ErasureFreshProviderUnavailable catch (error) {
          expect(error.toString(), isNot(contains('private')));
        }
        expect(ports.logoutCalls, 0);
      });
    });
  }
}
