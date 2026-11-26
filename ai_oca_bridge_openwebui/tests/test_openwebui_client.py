# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

import requests

from odoo.exceptions import UserError, ValidationError
from odoo.tests import common, mute_logger


class TestOpenWebUIClient(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "OpenWebUI client test",
                "url": "https://openwebui.example/api/chat/completions",
                "auth_type": "token",
                "auth_token": "test-token",
                "payload_type": "openwebui",
                "usage": "none",
                "result_kind": "immediate",
                "result_type": "none",
                "openwebui_model": "test-model",
            }
        )

    def _response(self, content="Answer"):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": content}}]}
        return response

    def test_chat_completion_sends_system_and_returns_text_blocks(self):
        self.bridge.openwebui_system_prompt = "Site-wide instructions"
        response = self._response(
            [
                {"type": "text", "text": "First"},
                {"type": "output_text", "text": "Second"},
            ]
        )
        with mock.patch("requests.request", return_value=response) as request_mock:
            result = self.bridge._openwebui_chat_completion(
                [{"role": "user", "content": "Question"}]
            )
        self.assertEqual(result, "First\nSecond")
        args, kwargs = request_mock.call_args
        self.assertEqual(
            args[:2],
            ("POST", "https://openwebui.example/api/chat/completions"),
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(kwargs["json"]["model"], "test-model")
        self.assertEqual(
            kwargs["json"]["messages"],
            [
                {"role": "system", "content": "Site-wide instructions"},
                {"role": "user", "content": "Question"},
            ],
        )
        self.assertFalse(kwargs["json"]["stream"])

    def test_basic_authentication_is_passed_to_requests(self):
        self.bridge.write(
            {
                "auth_type": "basic",
                "auth_username": "api-user",
                "auth_password": "secret",
            }
        )
        with mock.patch(
            "requests.request", return_value=self._response()
        ) as request_mock:
            self.bridge._openwebui_chat_completion([])
        self.assertEqual(request_mock.call_args.kwargs["auth"], ("api-user", "secret"))

    def test_missing_basic_credentials_are_reported(self):
        self.bridge.write({"auth_type": "basic", "auth_username": False})
        with self.assertRaisesRegex(UserError, "basic authentication is incomplete"):
            self.bridge._openwebui_request("GET", "/api/models")

    @mute_logger("odoo.addons.ai_oca_bridge_openwebui.models.openwebui_client")
    def test_http_error_is_wrapped_without_leaking_credentials(self):
        with mock.patch(
            "requests.request", side_effect=requests.ConnectionError("private url")
        ):
            with self.assertRaisesRegex(UserError, "could not generate a response"):
                self.bridge._openwebui_chat_completion([])

    @mute_logger("odoo.addons.ai_oca_bridge_openwebui.models.openwebui_client")
    def test_empty_and_malformed_responses_are_reported(self):
        with mock.patch("requests.request", return_value=self._response("  ")):
            with self.assertRaisesRegex(UserError, "empty response"):
                self.bridge._openwebui_chat_completion([])
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError("invalid JSON")
        with mock.patch("requests.request", return_value=response):
            with self.assertRaisesRegex(UserError, "could not generate a response"):
                self.bridge._openwebui_chat_completion([])
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {}
        with mock.patch("requests.request", return_value=response):
            with self.assertRaisesRegex(UserError, "could not generate a response"):
                self.bridge._openwebui_chat_completion([])

    def test_missing_model_and_connection_settings_are_rejected(self):
        self.bridge.openwebui_model = False
        with self.assertRaises(ValidationError):
            self.bridge._openwebui_check_model()
        self.bridge.url = False
        with self.assertRaisesRegex(UserError, "URL is not configured"):
            self.bridge._openwebui_request("GET", "/api/models")
        self.bridge.url = "https://openwebui.example/api/chat/completions"
        self.bridge.auth_token = False
        with self.assertRaisesRegex(UserError, "API token is missing"):
            self.bridge._openwebui_request("GET", "/api/models")

    def test_model_and_tool_catalog_selections_are_resolved(self):
        model = self.env["ai.openwebui.model"].create(
            {"name": "Catalog model", "external_id": "catalog-model"}
        )
        tool = self.env["ai.openwebui.tool"].create(
            {"name": "Catalog tool", "external_id": "catalog-tool"}
        )
        self.bridge.write(
            {
                "openwebui_model_id": model.id,
                "openwebui_tool_record_ids": [(6, 0, [tool.id])],
                "openwebui_tool_ids": "manual-tool",
            }
        )
        self.assertEqual(self.bridge._openwebui_model_name(), "catalog-model")
        self.assertEqual(self.bridge._openwebui_tool_ids(), ["catalog-tool"])
        self.bridge.openwebui_tool_record_ids = False
        self.assertEqual(self.bridge._openwebui_tool_ids(), ["manual-tool"])

    def test_openwebui_does_not_require_an_ir_model_target(self):
        self.assertFalse(self.bridge._get_model_fields()["model_required"])

    def test_invalid_bridge_result_configuration_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.bridge.write({"result_kind": "async"})
        with self.assertRaises(ValidationError):
            self.bridge.write({"result_type": "message"})

    def test_generic_payload_is_only_available_for_sample_display(self):
        sample = self.bridge.with_context(
            sample_payload=True
        )._prepare_payload_openwebui()
        self.assertEqual(sample["model"], "test-model")
        self.assertEqual(sample["messages"], [])
        with self.assertRaises(ValidationError):
            self.bridge._prepare_payload_openwebui()
