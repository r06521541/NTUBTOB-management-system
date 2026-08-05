import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

from linebot.v3.exceptions import InvalidSignatureError


FUNCTION_DIR = Path(__file__).resolve().parents[1]


def load_module(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, FUNCTION_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WebhookIngressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(FUNCTION_DIR))

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(FUNCTION_DIR))

    def setUp(self):
        self.dispatch = Mock()
        self.webhook_module = types.SimpleNamespace(handle_event=self.dispatch)
        self.original_webhook = sys.modules.get("webhook")
        self.original_functions_framework = sys.modules.get("functions_framework")
        sys.modules["webhook"] = self.webhook_module
        sys.modules["functions_framework"] = types.SimpleNamespace(
            http=lambda function: function
        )
        self.main_module = load_module("line_webhook_main_test", "main.py")
        self.app_module = load_module("line_webhook_app_test", "app.py")
        self.app_module.app.config.update(TESTING=False)

    def tearDown(self):
        if self.original_webhook is None:
            sys.modules.pop("webhook", None)
        else:
            sys.modules["webhook"] = self.original_webhook
        if self.original_functions_framework is None:
            sys.modules.pop("functions_framework", None)
        else:
            sys.modules["functions_framework"] = self.original_functions_framework

    def make_request(self, signature=None, body='{"events": []}'):
        headers = {}
        if signature is not None:
            headers["X-Line-Signature"] = signature
        request = Mock()
        request.headers = headers
        request.get_data.return_value = body
        return request

    def assert_rejected_without_dispatch(self, request):
        response = self.main_module.main(request)

        self.assertEqual(("Bad Request", 400), response)
        self.dispatch.assert_not_called()
        request.get_data.assert_not_called()

    def test_production_entry_rejects_missing_signature(self):
        self.assert_rejected_without_dispatch(self.make_request())

    def test_production_entry_rejects_blank_signature(self):
        self.assert_rejected_without_dispatch(self.make_request("  "))

    def test_production_entry_rejects_invalid_signature(self):
        self.dispatch.side_effect = InvalidSignatureError("invalid")
        request = self.make_request("fake-signature")

        response = self.main_module.main(request)

        self.assertEqual(("Bad Request", 400), response)
        self.dispatch.assert_called_once_with('{"events": []}', "fake-signature")

    def test_production_entry_accepts_dispatched_request(self):
        request = self.make_request("fake-signature")

        response = self.main_module.main(request)

        self.assertEqual(("OK", 200), response)
        self.dispatch.assert_called_once_with('{"events": []}', "fake-signature")

    def test_production_entry_does_not_hide_unexpected_failure(self):
        self.dispatch.side_effect = RuntimeError("sensitive request data")

        with self.assertRaisesRegex(RuntimeError, "Webhook dispatch failed") as raised:
            self.main_module.main(self.make_request("fake-signature"))
        self.assertNotIn("sensitive request data", str(raised.exception))

    def post_local(self, signature=None):
        headers = {}
        if signature is not None:
            headers["X-Line-Signature"] = signature
        with self.app_module.app.test_client() as client:
            return client.post("/", data='{"events": []}', headers=headers)

    def test_local_entry_rejects_missing_signature(self):
        response = self.post_local()

        self.assertEqual(400, response.status_code)
        self.assertEqual("Bad Request", response.get_data(as_text=True))
        self.dispatch.assert_not_called()

    def test_local_entry_rejects_blank_signature(self):
        response = self.post_local("  ")

        self.assertEqual(400, response.status_code)
        self.assertEqual("Bad Request", response.get_data(as_text=True))
        self.dispatch.assert_not_called()

    def test_local_entry_rejects_invalid_signature(self):
        self.dispatch.side_effect = InvalidSignatureError("invalid")

        response = self.post_local("fake-signature")

        self.assertEqual(400, response.status_code)
        self.assertEqual("Bad Request", response.get_data(as_text=True))
        self.dispatch.assert_called_once_with('{"events": []}', "fake-signature")

    def test_local_entry_accepts_dispatched_request(self):
        response = self.post_local("fake-signature")

        self.assertEqual(200, response.status_code)
        self.assertEqual("OK", response.get_data(as_text=True))
        self.dispatch.assert_called_once_with('{"events": []}', "fake-signature")

    def test_local_entry_returns_500_for_unexpected_failure(self):
        self.dispatch.side_effect = RuntimeError("sensitive request data")

        response = self.post_local("fake-signature")

        self.assertEqual(500, response.status_code)
        self.assertNotIn("sensitive request data", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
