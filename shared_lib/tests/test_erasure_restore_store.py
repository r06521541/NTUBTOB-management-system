"""Fictional discovery-shaped SDK and actual media downloader; never network."""

import json
import traceback
import unittest
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, unquote, urlsplit

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from shared_module.erasure_restore_binding import RestoreBinding
from shared_module.portal_data.erasure_fulfillment import PendingRestoreRecord
from shared_module.portal_data.erasure_person_fulfillment import PersonRestoreRecord
from shared_module.portal_data.erasure_restore_store import (
    GcsErasureRestorePurger,
    GcsErasureRestoreStore,
    RestoreObjectVersion,
    RestoreStoreRejected,
    RestoreStoreUnavailable,
)

JOB = "00000000-0000-4000-8000-000000000001"
ITEM = "00000000-0000-4000-8000-000000000002"
GENERATION = "00000000-0000-4000-8000-000000000003"
NAMESPACE = "00000000-0000-4000-8000-000000000004"
BUCKET = "fictional-restore-custody"
NAME = "account-erasure-restore/v1/" + NAMESPACE + "/" + ITEM + ".json"
PRIVATE_MARKER = "fictional-private-provider-body"


def pending():
    return PendingRestoreRecord(
        JOB, ITEM, "a" * 64, GENERATION, RestoreBinding(1, "fictional", "b" * 64)
    )


def person():
    return PersonRestoreRecord(
        JOB,
        ITEM,
        "a" * 64,
        GENERATION,
        42,
        NAMESPACE,
        RestoreBinding(1, "fictional", "b" * 64),
    )


class FakeExecute:
    def __init__(self, callback):
        self.callback = callback
        self.retries = []

    def execute(self, *, num_retries):
        self.retries.append(num_retries)
        return self.callback()


class FakeObjects:
    def __init__(self):
        self.blob = b""
        self.metadata = {}
        self.inserts = []
        self.gets = []
        self.media_gets = []
        self.http_calls = []
        self.insert_error = None
        self.metadata_error = None
        self.media_error = None
        self.media_payload = None
        self.response_headers = None
        self.media_status = 206
        self.insert_reply = None

    def insert(self, **kwargs):
        self.inserts.append(kwargs)

        def upload():
            if self.insert_error is not None:
                raise self.insert_error
            media = kwargs["media_body"]
            self.blob = media.getbytes(0, media.size())
            self.metadata = {
                "bucket": kwargs["bucket"],
                "name": kwargs["body"]["name"],
                "generation": "7",
                "size": str(len(self.blob)),
            }
            return (
                self.insert_reply
                if self.insert_reply is not None
                else dict(self.metadata)
            )

        self.insert_request = FakeExecute(upload)
        return self.insert_request

    def get(self, **kwargs):
        self.gets.append(kwargs)

        def metadata():
            if self.metadata_error is not None:
                raise self.metadata_error
            return dict(self.metadata)

        self.metadata_request = FakeExecute(metadata)
        return self.metadata_request

    def get_media(self, **kwargs):
        self.media_gets.append(kwargs)
        # Real MediaIoBaseDownload calls http.request, not request.execute.
        return SimpleNamespace(
            uri="https://fictional.invalid/media?generation=" + kwargs["generation"],
            headers={},
            http=self,
            execute=Mock(
                side_effect=AssertionError("unbounded media execute forbidden")
            ),
        )

    def request(self, uri, method, *, headers):
        self.http_calls.append((uri, method, headers))
        if self.media_error is not None:
            raise self.media_error
        payload = self.blob if self.media_payload is None else self.media_payload
        response = self.response_headers
        if response is None:
            response = {"content-range": f"bytes 0-{len(payload)-1}/{len(payload)}"}
        return (
            httplib2.Response({"status": str(self.media_status), **response}),
            payload,
        )

    def replace_blob(self, data):
        self.blob = data
        self.metadata["size"] = str(len(data))


class RestoreStoreTests(unittest.TestCase):
    def setUp(self):
        self.objects = FakeObjects()
        self.client = Mock()
        self.client.objects.return_value = self.objects
        self.store = GcsErasureRestoreStore(
            client=self.client, bucket=BUCKET, namespace=NAMESPACE
        )

    def roundtrip(self, record):
        identifier = self.store.put(record)
        self.assertEqual(identifier, record.item_id)
        # Read does not depend on a previous put or a mutable local receipt map.
        restored = GcsErasureRestoreStore(
            client=self.client, bucket=BUCKET, namespace=NAMESPACE
        ).read(identifier)
        self.assertIs(type(restored), type(record))
        self.assertEqual(restored, record)
        return restored

    def test_constructor_performs_no_sdk_io(self):
        self.client.objects.assert_not_called()
        for changes in (
            {"bucket": "../bad"},
            {"namespace": "AAAAAAAA-0000-4000-8000-000000000004"},
            {"client": None},
        ):
            with self.subTest(changes=changes), self.assertRaises(RestoreStoreRejected):
                GcsErasureRestoreStore(
                    **{
                        **dict(client=self.client, bucket=BUCKET, namespace=NAMESPACE),
                        **changes,
                    }
                )
        self.client.objects.assert_not_called()

    def test_actual_static_discovery_wire_uses_create_only_multipart_and_pinned_range(
        self,
    ):
        test = self

        class WireTransport:
            def __init__(self):
                self.calls = []
                self.blob = None
                self.metadata = None

            def request(self, uri, method="GET", body=None, headers=None, **kwargs):
                # Real SDK formatting, fictional transport only. build() is
                # static-discovery and supplied http, so no discovery/ADC I/O.
                self.calls.append((uri, method))
                parsed = urlsplit(uri)
                query = parse_qs(parsed.query)
                test.assertEqual(parsed.hostname, "storage.googleapis.com")
                if method == "POST":
                    test.assertEqual(
                        parsed.path, "/upload/storage/v1/b/" + BUCKET + "/o"
                    )
                    test.assertEqual(query["ifGenerationMatch"], ["0"])
                    test.assertEqual(query["uploadType"], ["multipart"])
                    test.assertEqual(query["fields"], ["bucket,name,generation,size"])
                    content_type = {
                        key.lower(): value for key, value in headers.items()
                    }["content-type"]
                    payload = body.encode("utf-8") if type(body) is str else body
                    message = BytesParser(policy=policy.default).parsebytes(
                        b"Content-Type: "
                        + content_type.encode("ascii")
                        + b"\r\n\r\n"
                        + payload
                    )
                    parts = list(message.iter_parts())
                    test.assertEqual(len(parts), 2)
                    test.assertEqual(
                        json.loads(parts[0].get_payload(decode=True)),
                        {"name": NAME, "contentType": "application/json"},
                    )
                    self.blob = parts[1].get_payload(decode=True)
                    self.metadata = {
                        "bucket": BUCKET,
                        "name": NAME,
                        "generation": "23",
                        "size": str(len(self.blob)),
                    }
                    return (
                        httplib2.Response(
                            {"status": "200", "content-type": "application/json"}
                        ),
                        json.dumps(self.metadata).encode(),
                    )
                test.assertEqual(method, "GET")
                test.assertEqual(
                    unquote(parsed.path), "/storage/v1/b/" + BUCKET + "/o/" + NAME
                )
                if query.get("alt") == ["media"]:
                    test.assertEqual(query["generation"], ["23"])
                    test.assertEqual(headers["range"], "bytes=0-4095")
                    return (
                        httplib2.Response(
                            {
                                "status": "206",
                                "content-range": f"bytes 0-{len(self.blob)-1}/{len(self.blob)}",
                            }
                        ),
                        self.blob,
                    )
                test.assertEqual(query["fields"], ["bucket,name,generation,size"])
                return (
                    httplib2.Response(
                        {"status": "200", "content-type": "application/json"}
                    ),
                    json.dumps(self.metadata).encode(),
                )

        for record in (pending(), person()):
            with self.subTest(kind=type(record).__name__):
                transport = WireTransport()
                client = build(
                    "storage",
                    "v1",
                    http=transport,
                    static_discovery=True,
                    cache_discovery=False,
                )
                store = GcsErasureRestoreStore(
                    client=client, bucket=BUCKET, namespace=NAMESPACE
                )
                self.assertEqual(transport.calls, [])
                self.assertEqual(store.read(store.put(record)), record)
                self.assertEqual(
                    [call[1] for call in transport.calls], ["POST", "GET", "GET"]
                )

    def test_both_exact_dtos_roundtrip_create_only_and_generation_pinned(self):
        for record in (pending(), person()):
            with self.subTest(kind=type(record).__name__):
                self.roundtrip(record)
                insert = self.objects.inserts[-1]
                self.assertEqual(insert["bucket"], BUCKET)
                self.assertEqual(
                    insert["body"], {"name": NAME, "contentType": "application/json"}
                )
                self.assertEqual(insert["ifGenerationMatch"], 0)
                self.assertFalse(insert["media_body"].resumable())
                self.assertEqual(self.objects.insert_request.retries, [0])
                self.assertEqual(
                    self.objects.gets[-1],
                    {
                        "bucket": BUCKET,
                        "object": NAME,
                        "fields": "bucket,name,generation,size",
                    },
                )
                self.assertEqual(self.objects.metadata_request.retries, [0])
                self.assertEqual(
                    self.objects.media_gets[-1],
                    {"bucket": BUCKET, "object": NAME, "generation": "7"},
                )
                self.assertEqual(self.objects.http_calls[-1][1], "GET")
                self.assertEqual(
                    self.objects.http_calls[-1][2]["range"], "bytes=0-4095"
                )
                self.assertLessEqual(len(self.objects.blob), 4096)
                self.assertNotIn(b"subject", self.objects.blob)
                self.assertNotIn(b"expiry", self.objects.blob)

    def test_put_rejects_wrong_dto_types_and_fields_without_io(self):
        for record in (
            object(),
            vars(pending()),
            replace(pending(), item_id=ITEM + "\n"),
            replace(pending(), scope_hash="A" * 64),
            replace(pending(), binding=RestoreBinding(True, "fictional", "b" * 64)),
            replace(pending(), binding=RestoreBinding(1, "x" * 4097, "b" * 64)),
            replace(person(), identity_id=True),
            replace(person(), identity_id=2**63),
        ):
            with (
                self.subTest(kind=type(record).__name__),
                self.assertRaises(RestoreStoreRejected),
            ):
                self.store.put(record)
        self.client.objects.assert_not_called()

    def test_read_rejects_noncanonical_identifiers_before_io(self):
        for identifier in (None, 1, ITEM.replace("-", ""), ITEM + "\n", "../" + ITEM):
            with (
                self.subTest(identifier=identifier),
                self.assertRaises(RestoreStoreRejected),
            ):
                self.store.read(identifier)
        self.client.objects.assert_not_called()

    def test_payload_schema_duplicates_unknown_fields_type_and_binding_reject(self):
        self.store.put(pending())
        original = json.loads(self.objects.blob)
        variants = []
        for field, value in (
            ("version", True),
            ("kind", "unknown"),
            ("namespace", GENERATION),
        ):
            changed = json.loads(json.dumps(original))
            changed[field] = value
            variants.append(json.dumps(changed).encode())
        for field, value in (
            ("item_id", JOB),
            ("scope_hash", "a" * 64 + "\n"),
            ("generation", "not-a-uuid"),
        ):
            changed = json.loads(json.dumps(original))
            changed["record"][field] = value
            variants.append(json.dumps(changed).encode())
        changed = json.loads(json.dumps(original))
        changed["record"]["provider_subject"] = PRIVATE_MARKER
        variants.append(json.dumps(changed).encode())
        changed = json.loads(json.dumps(original))
        del changed["record"]["job_id"]
        variants.append(json.dumps(changed).encode())
        raw = json.dumps(original, separators=(",", ":")).encode()
        variants.extend(
            (
                raw.replace(b'"version":1', b'"version":1,"version":1', 1),
                raw.replace(
                    b'"key_id":"fictional"',
                    b'"key_id":"fictional","key_id":"fictional"',
                ),
                b'{"version":NaN}',
                b"[]",
                b"\xff",
                raw[:-1],
            )
        )
        for payload in variants:
            with (
                self.subTest(size=len(payload)),
                self.assertRaises(RestoreStoreUnavailable),
            ):
                self.objects.replace_blob(payload)
                self.store.read(ITEM)

    def test_person_schema_does_not_accept_bool_or_out_of_range_identity(self):
        self.store.put(person())
        original = json.loads(self.objects.blob)
        for value in (True, 0, -1, 2**63, "42", 42.0):
            with self.subTest(value=value), self.assertRaises(RestoreStoreUnavailable):
                payload = json.loads(json.dumps(original))
                payload["record"]["identity_id"] = value
                self.objects.replace_blob(json.dumps(payload).encode())
                self.store.read(ITEM)

    def test_metadata_invalid_size_generation_or_object_binding_stops_before_media(
        self,
    ):
        self.store.put(pending())
        original = dict(self.objects.metadata)
        for field, value in (
            ("bucket", "different-bucket"),
            ("name", NAME + ".other"),
            ("generation", "0"),
            ("generation", "-1"),
            ("generation", "07"),
            ("generation", 7),
            ("generation", "7\n"),
            ("generation", "9" * 21),
            ("size", "0"),
            ("size", "4097"),
            ("size", True),
            ("size", "01"),
        ):
            with (
                self.subTest(field=field, value=value),
                self.assertRaises(RestoreStoreUnavailable),
            ):
                self.objects.metadata = {**original, field: value}
                self.store.read(ITEM)
        self.assertEqual(self.objects.media_gets, [])

    def test_insert_invalid_ack_is_unknown_not_success_or_retry(self):
        for reply in ({}, {"generation": "7"}):
            self.objects.insert_reply = reply
            with self.assertRaises(RestoreStoreUnavailable):
                self.store.put(pending())
            self.assertEqual(self.objects.insert_request.retries, [0])
        self.assertEqual(len(self.objects.inserts), 2)
        self.assertEqual(self.objects.gets, [])

    def test_collision_and_timeout_never_retry_or_read_as_success(self):
        for error in (
            HttpError(httplib2.Response({"status": "412"}), PRIVATE_MARKER.encode()),
            TimeoutError(PRIVATE_MARKER),
        ):
            self.objects.insert_error = error
            with self.assertRaises(RestoreStoreUnavailable) as caught:
                self.store.put(pending())
            self.assertNotIn(PRIVATE_MARKER, str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)
            self.assertEqual(self.objects.insert_request.retries, [0])
        self.assertEqual(len(self.objects.inserts), 2)
        self.assertEqual(self.objects.gets, [])
        self.assertEqual(self.objects.http_calls, [])

    def test_oversize_media_is_not_accumulated_or_retried(self):
        self.store.put(pending())
        self.objects.media_payload = b"x" * 4097
        with self.assertRaises(RestoreStoreUnavailable):
            self.store.read(ITEM)
        self.assertEqual(len(self.objects.http_calls), 1)

    def test_truncated_or_wrong_progress_never_downloads_another_chunk(self):
        self.store.put(pending())
        size = len(self.objects.blob)
        for payload, headers in (
            (self.objects.blob[:-1], {"content-range": f"bytes 0-{size-2}/{size}"}),
            (self.objects.blob, {"content-range": f"bytes 0-{size-1}/{size+1}"}),
            (self.objects.blob, {}),
            (b"", {"content-range": "bytes */0"}),
        ):
            before = len(self.objects.http_calls)
            self.objects.media_payload, self.objects.response_headers = payload, headers
            with (
                self.subTest(size=len(payload)),
                self.assertRaises(RestoreStoreUnavailable),
            ):
                self.store.read(ITEM)
            self.assertEqual(len(self.objects.http_calls), before + 1)

    def test_generation_pin_failure_and_read_timeout_have_no_retry_or_body_leak(self):
        self.store.put(pending())
        self.objects.media_status = 412
        self.objects.media_payload = PRIVATE_MARKER.encode()
        with self.assertRaises(RestoreStoreUnavailable) as caught:
            self.store.read(ITEM)
        self.assertNotIn(
            PRIVATE_MARKER, "".join(traceback.format_exception(caught.exception))
        )
        self.assertEqual(self.objects.media_gets[-1]["generation"], "7")
        self.assertEqual(len(self.objects.http_calls), 1)
        self.objects.media_error = TimeoutError(PRIVATE_MARKER)
        with self.assertRaises(RestoreStoreUnavailable) as caught:
            self.store.read(ITEM)
        self.assertNotIn(
            PRIVATE_MARKER, "".join(traceback.format_exception(caught.exception))
        )
        self.assertEqual(len(self.objects.http_calls), 2)

    def test_metadata_failure_is_safe_and_does_not_fetch_media(self):
        self.objects.metadata_error = RuntimeError(PRIVATE_MARKER)
        with self.assertRaises(RestoreStoreUnavailable) as caught:
            self.store.read(ITEM)
        self.assertNotIn(
            PRIVATE_MARKER, "".join(traceback.format_exception(caught.exception))
        )
        self.assertEqual(self.objects.metadata_request.retries, [0])
        self.assertEqual(self.objects.media_gets, [])


class FakePurgeObjects(FakeObjects):
    """No real storage: deletion can fail before or after the fictional effect."""

    def __init__(self):
        super().__init__()
        self.deletes = []
        self.delete_error = None
        self.delete_reply = ""
        self.after_delete = None

    def delete(self, **kwargs):
        self.deletes.append(kwargs)

        def remove():
            if self.after_delete is not None:
                self.after_delete()
            if self.delete_error is not None:
                raise self.delete_error
            return self.delete_reply

        self.delete_request = FakeExecute(remove)
        return self.delete_request


class RestoreVersionTests(unittest.TestCase):
    def setUp(self):
        self.objects = FakePurgeObjects()
        self.client = Mock()
        self.client.objects.return_value = self.objects
        self.store = GcsErasureRestoreStore(
            client=self.client, bucket=BUCKET, namespace=NAMESPACE
        )
        self.purger = self.new_purger()

    def new_purger(self):
        return GcsErasureRestorePurger(
            client=self.client, bucket=BUCKET, namespace=NAMESPACE
        )

    def version(self, record=None):
        record = record or pending()
        self.store.put(record)
        readback = self.store.read_versioned(record.item_id)
        self.assertEqual(readback.record, record)
        self.assertEqual(self.store.read(record.item_id), record)
        self.assertEqual(
            readback.version,
            RestoreObjectVersion(BUCKET, NAMESPACE, ITEM, "7", len(self.objects.blob)),
        )
        return readback.version

    @staticmethod
    def http_error(status):
        return HttpError(
            httplib2.Response({"status": str(status)}), PRIVATE_MARKER.encode()
        )

    def assert_outcome(self, result, stage, classification, dispatched):
        self.assertEqual(
            vars(result),
            {
                "stage": stage,
                "classification": classification,
                "delete_dispatched": dispatched,
                "next_action": "read_only_version_review",
            },
        )
        for secret in (PRIVATE_MARKER, BUCKET, NAMESPACE, ITEM):
            self.assertNotIn(secret, repr(result))

    def test_separate_authorities_constructor_no_io_and_versioned_dto_compatibility(
        self,
    ):
        self.client.objects.assert_not_called()
        self.assertFalse(hasattr(self.store, "purge"))
        self.assertFalse(hasattr(self.store, "delete"))
        self.assertFalse(hasattr(self.purger, "put"))
        for record in (pending(), person()):
            version = self.version(record)
            self.assertNotIn(ITEM, repr(version))
            readback = self.store.read_versioned(ITEM)
            self.assertNotIn(ITEM, repr(readback))
            with self.assertRaises(AttributeError):
                version.generation = "8"

    def test_active_version_delete_has_precondition_but_no_historical_selector(self):
        version = self.version()
        result = self.purger.purge(version)
        self.assert_outcome(result, "delete", "active_version_removed", True)
        self.assertEqual(
            self.objects.deletes,
            [{"bucket": BUCKET, "object": NAME, "ifGenerationMatch": "7"}],
        )
        self.assertEqual(self.objects.delete_request.retries, [0])
        self.assertEqual(
            self.objects.gets[-1],
            {"bucket": BUCKET, "object": NAME, "fields": "bucket,name,generation,size"},
        )
        before = len(self.objects.gets)
        self.assertEqual(self.purger.purge(version), result)
        self.assertEqual(len(self.objects.deletes), 1)
        self.assertEqual(len(self.objects.gets), before)

    def test_invalid_version_or_wrong_namespace_never_calls_sdk(self):
        version = self.version()
        invalid = [
            None,
            object(),
            vars(version),
            replace(version, bucket="other-bucket"),
            replace(version, namespace=JOB),
            replace(version, item_id=ITEM + "\n"),
            replace(version, item_id="../other"),
            replace(version, generation="07"),
            replace(version, generation="0"),
            replace(version, generation=7),
            replace(version, generation=str(2**64)),
            replace(version, generation="7\n"),
            replace(version, size=True),
            replace(version, size=0),
            replace(version, size=4097),
        ]
        self.client.reset_mock()
        for bad in invalid:
            with self.subTest(type=type(bad).__name__):
                for action in (self.purger.purge, self.purger.read_version_presence):
                    with self.assertRaises(RestoreStoreRejected):
                        action(bad)
        self.client.objects.assert_not_called()
        self.assertEqual(self.objects.deletes, [])

    def test_stale_or_invalid_preflight_never_deletes(self):
        version = self.version()
        for field, value, expected in (
            ("generation", "8", "version_conflict"),
            ("size", str(version.size + 1), "version_conflict"),
            ("name", "other-object", "metadata_rejected"),
            ("generation", "0", "metadata_rejected"),
        ):
            with self.subTest(field=field, value=value):
                original = self.objects.metadata.copy()
                self.objects.metadata[field] = value
                self.assert_outcome(
                    self.new_purger().purge(version), "preflight", expected, False
                )
                self.objects.metadata = original
        self.assertEqual(self.objects.deletes, [])

    def test_preflight_404_412_and_unknown_are_not_absence_or_retry_authority(self):
        version = self.version()
        for error, expected in (
            (self.http_error(404), "current_not_found"),
            (self.http_error(412), "version_conflict"),
            (TimeoutError(PRIVATE_MARKER), "metadata_unavailable"),
        ):
            self.objects.metadata_error = error
            self.assert_outcome(
                self.new_purger().purge(version), "preflight", expected, False
            )
        self.assertEqual(self.objects.deletes, [])

    def test_delete_404_412_timeout_and_rejection_keep_fixed_one_shot_facts(self):
        version = self.version()
        for error, expected in (
            (self.http_error(404), "current_not_found"),
            (self.http_error(412), "version_conflict"),
            (self.http_error(403), "delete_rejected"),
            (self.http_error(500), "delete_outcome_unknown"),
            (TimeoutError(PRIVATE_MARKER), "delete_outcome_unknown"),
        ):
            with self.subTest(expected=expected):
                purger = self.new_purger()
                self.objects.delete_error = error
                result = purger.purge(version)
                self.assert_outcome(result, "delete", expected, True)
                count = len(self.objects.deletes)
                self.assertEqual(purger.purge(version), result)
                # Changing an untrusted size cannot bypass the per-version fence.
                self.assertEqual(
                    purger.purge(replace(version, size=version.size + 1)), result
                )
                self.assertEqual(len(self.objects.deletes), count)
                self.assertEqual(self.objects.delete_request.retries, [0])

    def test_lost_delete_ack_presence_observation_does_not_rewrite_or_resend(self):
        version = self.version()
        self.objects.after_delete = lambda: setattr(
            self.objects, "metadata_error", self.http_error(404)
        )
        self.objects.delete_error = TimeoutError(PRIVATE_MARKER)
        unknown = self.purger.purge(version)
        self.assert_outcome(unknown, "delete", "delete_outcome_unknown", True)
        presence = self.purger.read_version_presence(version)
        self.assert_outcome(presence, "presence", "version_not_found", False)
        self.assertEqual(self.objects.gets[-1]["generation"], "7")
        self.assertEqual(self.purger.purge(version), unknown)
        self.assertEqual(len(self.objects.deletes), 1)

    def test_presence_is_exact_readonly_and_does_not_claim_all_copies_absent(self):
        version = self.version()
        self.assert_outcome(
            self.purger.read_version_presence(version),
            "presence",
            "version_present",
            False,
        )
        self.assertEqual(
            self.objects.gets[-1],
            {
                "bucket": BUCKET,
                "object": NAME,
                "generation": "7",
                "fields": "bucket,name,generation,size",
            },
        )
        self.objects.metadata["generation"] = "8"
        self.assert_outcome(
            self.purger.read_version_presence(version),
            "presence",
            "version_conflict",
            False,
        )
        for error, expected in (
            (self.http_error(404), "version_not_found"),
            (self.http_error(412), "version_conflict"),
            (RuntimeError(PRIVATE_MARKER), "metadata_unavailable"),
        ):
            self.objects.metadata_error = error
            self.assert_outcome(
                self.purger.read_version_presence(version), "presence", expected, False
            )
        self.assertEqual(self.objects.deletes, [])

    def test_malformed_delete_ack_is_unknown_and_reentrant_call_cannot_dispatch(self):
        version = self.version()
        nested = []
        self.objects.after_delete = lambda: nested.append(self.purger.purge(version))
        self.objects.delete_reply = {"private": PRIVATE_MARKER}
        result = self.purger.purge(version)
        self.assert_outcome(result, "delete", "delete_outcome_unknown", True)
        self.assertEqual(nested, [result])
        self.assertEqual(len(self.objects.deletes), 1)

    def test_actual_discovery_delete_wire_and_generation_pinned_presence_no_network(
        self,
    ):
        version = self.version()
        calls = []
        metadata = self.objects.metadata.copy()

        class Transport:
            def request(inner, uri, method="GET", body=None, headers=None, **kwargs):
                parts = urlsplit(uri)
                query = parse_qs(parts.query)
                calls.append((method, query))
                self.assertEqual(unquote(parts.path).split("/o/", 1)[1], NAME)
                if method == "DELETE":
                    self.assertEqual(query, {"ifGenerationMatch": ["7"]})
                    self.assertIsNone(body)
                    return httplib2.Response({"status": "204"}), b""
                self.assertEqual(method, "GET")
                return (
                    httplib2.Response({"status": "200"}),
                    json.dumps(metadata).encode(),
                )

        client = build(
            "storage",
            "v1",
            http=Transport(),
            static_discovery=True,
            cache_discovery=False,
        )
        purger = GcsErasureRestorePurger(
            client=client, bucket=BUCKET, namespace=NAMESPACE
        )
        self.assert_outcome(
            purger.purge(version), "delete", "active_version_removed", True
        )
        self.assert_outcome(
            purger.read_version_presence(version), "presence", "version_present", False
        )
        self.assertEqual([method for method, _ in calls], ["GET", "DELETE", "GET"])
        self.assertNotIn("generation", calls[0][1])
        self.assertEqual(calls[2][1]["generation"], ["7"])


if __name__ == "__main__":
    unittest.main()
