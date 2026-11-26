# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.ai_oca_bridge_openwebui_web_editor.controllers.main import (
    HtmlEditorOpenWebUI,
)


@tagged("post_install", "-at_install")
class TestHtmlEditorOpenWebUI(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "HTML Editor OpenWebUI",
                "active": True,
                "payload_type": "openwebui",
                "usage": "web_editor",
                "result_kind": "immediate",
                "result_type": "none",
                "url": "https://openwebui.example/api/chat/completions",
                "auth_type": "token",
                "auth_token": "test-token",
                "openwebui_model": "test-model",
            }
        )

    def test_route_forwards_history_and_returns_plain_text(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "Texte réécrit"}}]
        }
        request_proxy = SimpleNamespace(env=self.env)
        with (
            patch(
                "odoo.addons.ai_oca_bridge_openwebui_web_editor.controllers.main.request",
                request_proxy,
            ),
            patch("requests.request", return_value=response) as request_mock,
        ):
            controller = HtmlEditorOpenWebUI()
            result = HtmlEditorOpenWebUI.generate_text.__wrapped__(
                controller,
                "Make it professional",
                [{"role": "system", "content": "Keep the original meaning."}],
            )
        self.assertEqual(result, "Texte réécrit")
        payload = request_mock.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["messages"][-1]["content"], "Make it professional")
        self.assertEqual(
            payload["messages"][0]["content"], "Keep the original meaning."
        )
        self.assertFalse(payload["stream"])
