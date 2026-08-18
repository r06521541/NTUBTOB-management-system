import 'package:flutter_test/flutter_test.dart';
import 'package:ntubtob_fictional_client/foundation.dart';

void main() {
  test('capabilities inherit and fail closed', () {
    expect(CapabilityPolicy(Persona.basic).routes, isNot(contains('/officer')));
    expect(CapabilityPolicy(Persona.officer).routes, contains('/officer'));
    expect(CapabilityPolicy(Persona.admin).routes, contains('/officer'));
    expect(CapabilityPolicy(Persona.admin).routes, contains('/admin'));
  });
  test('fake repository is deterministic and offline read-only', () async {
    final repo = FakeRepository(lastSyncedAt: DateTime.utc(2026, 1, 2));
    final snapshot = await repo.readSnapshot();
    expect(snapshot.lastSyncedAt, DateTime.utc(2026, 1, 2));
    expect(snapshot.fixture['adminAnnouncement'], '系統公告預覽');
    expect(repo.pushEvents, isEmpty);
    expect(repo.submitOfflineMutation(), throwsStateError);
  });
}
