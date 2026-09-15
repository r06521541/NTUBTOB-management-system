"""Fictional GET-only ASC contract; no real account/network."""

import json
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlsplit

from tools import ios_native_asc as asc


def page(items=(), next_url=None):
    return {"data": list(items), "links": {"next": next_url}}


def item(kind, identity, **attrs):
    return {"id": identity, "type": kind, "attributes": attrs}


def ready_get(path):
    if urlsplit(path).path == "/v1/apps":
        return page([item("apps", "123", bundleId=asc.BUNDLE)])
    if "/betaGroups" in path:
        return page([item("betaGroups", "fictional-group", hasAccessToAllBuilds=False)])
    return page()


class PreflightTests(unittest.TestCase):
    def test_get_only_exact_app_and_both_duplicate_collections_before_groups(self):
        get = mock.Mock(side_effect=ready_get)
        self.assertEqual(asc.preflight(get, "1.2.3", "42"), "123")
        paths = [call.args[0] for call in get.call_args_list]
        self.assertEqual(len(paths), 4)
        self.assertIn("buildUploads", paths[1])
        self.assertEqual(parse_qs(urlsplit(paths[2]).query)["filter[version]"], ["42"])
        self.assertIn("betaGroups", paths[-1])

    def test_page_two_auto_access_is_not_missed(self):
        first = "/v1/apps/123/betaGroups"
        cursor = (
            "https://"
            + asc.HOST
            + first
            + "?"
            + urlencode({"limit": "200", "cursor": "second"})
        )

        def get(path):
            if first in path:
                if "cursor=" in path:
                    return page(
                        [item("betaGroups", "second", hasAccessToAllBuilds=True)]
                    )
                return page(
                    [item("betaGroups", "first", hasAccessToAllBuilds=False)], cursor
                )
            return ready_get(path)

        with self.assertRaises(asc.Failure) as caught:
            asc.preflight(get, "1.2.3", "42")
        self.assertEqual(caught.exception.reason, "AUTOMATIC_ACCESS_NOT_DISABLED")

    def test_missing_null_numeric_flags_and_wrong_app_stop(self):
        for attrs in ({}, {"hasAccessToAllBuilds": None}, {"hasAccessToAllBuilds": 0}):

            def get(path):
                return (
                    page([item("betaGroups", "g", **attrs)])
                    if "/betaGroups" in path
                    else ready_get(path)
                )

            with self.assertRaises(asc.Failure):
                asc.preflight(get, "1.2.3", "42")
        with self.assertRaises(asc.Failure):
            asc.preflight(
                lambda _: page([item("apps", "123", bundleId="wrong.app")]),
                "1.2.3",
                "42",
            )

    def test_any_matching_upload_or_build_stops_including_failed(self):
        for kind in ("buildUploads", "builds"):

            def get(path):
                if urlsplit(path).path.endswith("/" + kind):
                    return page([item(kind, "existing", state="FAILED")])
                return ready_get(path)

            with self.assertRaises(asc.Failure) as caught:
                asc.preflight(get, "1.2.3", "42")
            self.assertEqual(caught.exception.reason, "BUILD_ALREADY_EXISTS")

    def test_cursor_host_path_filters_and_duplicates_rejected(self):
        path = "/v1/apps/123/betaGroups"
        for url in (
            "https://evil.invalid" + path + "?limit=200&cursor=x",
            "https://" + asc.HOST + "/v1/apps/456/betaGroups?limit=200&cursor=x",
            "https://" + asc.HOST + path + "?limit=200&cursor=x&cursor=y",
            "https://" + asc.HOST + path + "?limit=200&cursor=x&filter[app]=456",
        ):
            with self.assertRaises(asc.Failure):
                asc.resources(lambda _: page([], url), path, {}, "betaGroups")
        duplicate = item("betaGroups", "same", hasAccessToAllBuilds=False)
        with self.assertRaises(asc.Failure):
            asc.resources(
                lambda _: page([duplicate, duplicate]), path, {}, "betaGroups"
            )


class TransportTests(unittest.TestCase):
    def reader(self, status=200, body=None):
        response = mock.Mock(status=status)
        response.read1.side_effect = [body or b'{"data":[],"links":{"next":null}}', b""]
        connection = mock.Mock()
        connection.getresponse.return_value = response
        factory = mock.Mock(return_value=connection)
        reader = asc.Reader(object(), connect=factory)
        return reader, factory, connection

    @mock.patch("tools.ios_testflight_inputs.asc_jwt")
    def test_fixed_host_get_no_body_and_no_token_output(self, token):
        token.return_value.value = "fictional-secret"
        reader, factory, connection = self.reader()
        self.assertEqual(reader.get("/v1/apps")["data"], [])
        self.assertEqual(factory.call_args.args, (asc.HOST,))
        self.assertEqual(connection.request.call_args.args, ("GET", "/v1/apps"))
        connection.close.assert_called_once()

    @mock.patch("tools.ios_testflight_inputs.asc_jwt")
    def test_http_reason_primary_and_connection_cleanup_both_retained(self, token):
        token.return_value.value = "fictional-secret"
        for status in (301, 401, 403, 404, 429, 500):
            reader, _, connection = self.reader(status)
            connection.close.side_effect = OSError("private-details")
            with self.assertRaises(asc.Failure) as caught:
                reader.get("/v1/apps")
            self.assertIn("HTTP_", caught.exception.reason)
            self.assertEqual(reader.cleanup_failures[0]["reason"], "CLOSE_FAILED")
            connection.getresponse.return_value.read1.assert_not_called()

    @mock.patch("tools.ios_testflight_inputs.asc_jwt")
    def test_body_limit_duplicate_json_and_deadline(self, token):
        token.return_value.value = "fictional-secret"
        for body in (b"x" * (asc.LIMIT + 1), b'{"data":[],"data":[]}'):
            reader, _, _ = self.reader(body=body)
            with self.assertRaises(asc.Failure):
                reader.get("/v1/apps")
        reader, factory, _ = self.reader()
        reader.deadline = 0
        with self.assertRaises(asc.Failure):
            reader.get("/v1/apps")
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
