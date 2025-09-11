# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase, JsonRpcException
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestOllama(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_oca_native_generate_ollama.connection", "http://localhost:11434"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_oca_native_generate_ollama.model", "llama2"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_oca_native_generate_ollama.headers",
            '{"Authorization": "Bearer YOUR_API_KEY"}',
        )

    @mute_logger("odoo.http")
    def test_connection_failure(self):
        """
        As we don't have a real Ollama server running,
        we expect a connection failure when trying to connect.
        """
        self.authenticate("admin", "admin")
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(
                "/html_editor/generate_text",
                params={
                    "prompt": "Hello, how are you?",
                    "conversation_history": [
                        {"role": "user", "content": "Hi!"},
                    ],
                },
            )

    def test_connection_ok(self):
        """
        Test with a mocked Ollama client to simulate a successful response.
        """
        self.authenticate("admin", "admin")
        with patch("ollama.Client.chat") as mock_chat:
            mock_chat.return_value.message.content = "I'm fine, thank you!"
            response = self.make_jsonrpc_request(
                "/html_editor/generate_text",
                params={
                    "prompt": "Hello, how are you?",
                    "conversation_history": [
                        {"role": "user", "content": "Hi!"},
                    ],
                },
            )
            mock_chat.assert_called_once()
        self.assertEqual("I'm fine, thank you!", response)

    def test_no_configuration(self):
        """
        If no configuration is set, the request should fallback to standard (with IAP)
        """
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_oca_native_generate_ollama.connection", ""
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_oca_native_generate_ollama.model", ""
        )
        self.authenticate("admin", "admin")
        with patch("odoo.addons.iap.tools.iap_tools.iap_jsonrpc") as mock_iap:
            mock_iap.return_value = {
                "content": "This is a response from IAP.",
                "status": "success",
            }
            response = self.make_jsonrpc_request(
                "/html_editor/generate_text",
                params={
                    "prompt": "Hello, how are you?",
                    "conversation_history": [
                        {"role": "user", "content": "Hi!"},
                    ],
                },
            )
        self.assertEqual("This is a response from IAP.", response)
