# Copyright 2026 Nitrokey GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

import openai

from odoo.tests import tagged
from odoo.tests.common import HttpCase, JsonRpcException
from odoo.tools import mute_logger

PARAMS = {
    "prompt": "Hello, how are you?",
    "conversation_history": [
        {"role": "user", "content": "Hi!"},
    ],
}


@tagged("post_install", "-at_install")
class TestOpenAI(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("ai_oca_native_generate_openai.url", "http://localhost:8000/v1")
        ICP.set_param("ai_oca_native_generate_openai.model", "llama3")
        ICP.set_param("ai_oca_native_generate_openai.api_key", "YOUR_API_KEY")
        ICP.set_param("ai_oca_native_generate_openai.temperature", "0.2")

    def test_connection_ok(self):
        """
        Test with a mocked OpenAI client to simulate a successful response.
        """
        self.authenticate("admin", "admin")
        with patch("openai.resources.chat.Completions.create") as mock_create:
            mock_create.return_value.choices[0].message.content = "I'm fine, thank you!"
            response = self.make_jsonrpc_request(
                "/html_editor/generate_text", params=PARAMS
            )
            mock_create.assert_called_once()
            kwargs = mock_create.call_args.kwargs
        self.assertEqual("I'm fine, thank you!", response)
        self.assertEqual(kwargs["model"], "llama3")
        self.assertEqual(kwargs["temperature"], 0.2)
        self.assertEqual(
            kwargs["messages"],
            [
                {"role": "user", "content": "Hi!"},
                {"role": "user", "content": "Hello, how are you?"},
            ],
        )

    def test_no_api_key_no_temperature(self):
        """
        The API key and the temperature are optional.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("ai_oca_native_generate_openai.api_key", "")
        ICP.set_param("ai_oca_native_generate_openai.temperature", "")
        self.authenticate("admin", "admin")
        with patch("openai.resources.chat.Completions.create") as mock_create:
            mock_create.return_value.choices[0].message.content = "Hello!"
            response = self.make_jsonrpc_request(
                "/html_editor/generate_text", params=PARAMS
            )
            kwargs = mock_create.call_args.kwargs
        self.assertEqual("Hello!", response)
        self.assertIs(kwargs["temperature"], openai.NOT_GIVEN)

    @mute_logger(
        "odoo.http", "odoo.addons.ai_oca_native_generate_openai.controllers.main"
    )
    def test_connection_failure(self):
        """
        Errors of the server are shown as a user error.
        """
        self.authenticate("admin", "admin")
        with patch("openai.resources.chat.Completions.create") as mock_create:
            mock_create.side_effect = openai.OpenAIError("Connection refused")
            with self.assertRaises(JsonRpcException) as error:
                self.make_jsonrpc_request("/html_editor/generate_text", params=PARAMS)
        self.assertEqual(error.exception.args[0], "odoo.exceptions.UserError")

    def test_no_configuration(self):
        """
        If no configuration is set, the request should fallback to standard (with IAP)
        """
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("ai_oca_native_generate_openai.url", "")
        ICP.set_param("ai_oca_native_generate_openai.model", "")
        self.authenticate("admin", "admin")
        with patch("odoo.addons.iap.tools.iap_tools.iap_jsonrpc") as mock_iap:
            mock_iap.return_value = {
                "content": "This is a response from IAP.",
                "status": "success",
            }
            response = self.make_jsonrpc_request(
                "/html_editor/generate_text", params=PARAMS
            )
        self.assertEqual("This is a response from IAP.", response)
