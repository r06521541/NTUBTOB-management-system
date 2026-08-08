import json
import unittest

from tools import phase_c_release_manifest as manifest
from tools import phase_c_transition_controller as transition


SHA = "a" * 40
FINGERPRINT = "b" * 64
REVISIONS = {
    "web_portal": "web-portal-00040-wm9",
    "line_webhook": "line-webhook-handler-00001-abc",
    "notify_cron": "notify-cronjob-service-00011-jpj",
}


class ReleaseManifestTests(unittest.TestCase):
    def test_manifest_is_redacted_and_uses_canonical_freeze_path(self):
        path = transition.canonical_transition_path()
        result = manifest.build_manifest(
            path[0],
            path[-2],
            source_commit=SHA,
            expected_source_commit=SHA,
            artifact_fingerprint=FINGERPRINT,
            expected_artifact_fingerprint=FINGERPRINT,
            current_revisions=REVISIONS, rollback_revisions=REVISIONS,
        )
        rendered = manifest.render_manifest(result)
        self.assertEqual(json.loads(rendered)["schema"], "phase-c-release-manifest-v1")
        self.assertEqual(
            result["steps"][0],
            {"service": "web_portal", "flag": "freeze", "value": True},
        )
        self.assertEqual(
            result["scheduler_boundary"], "no_scheduler_mutation_or_invocation"
        )
        self.assertNotIn("secret", rendered.lower())
        self.assertNotIn("token", rendered.lower())

    def test_invalid_revision_or_drift_fails_without_echoing_input(self):
        path = transition.canonical_transition_path()
        values = dict(REVISIONS)
        values["notify_cron"] = "credential-like-sentinel"
        with self.assertRaisesRegex(
            manifest.ReleaseManifestError, "invalid revision"
        ) as raised:
            manifest.build_manifest(
                path[0],
                path[0],
                source_commit=SHA,
                expected_source_commit=SHA,
                artifact_fingerprint=FINGERPRINT,
                expected_artifact_fingerprint=FINGERPRINT,
                current_revisions=values, rollback_revisions=REVISIONS,
            )
        self.assertNotIn(values["notify_cron"], str(raised.exception))

    def test_unsupported_render_field_fails_closed(self):
        with self.assertRaisesRegex(manifest.ReleaseManifestError, "unsupported"):
            manifest.render_manifest({"credential": "not-allowed"})
