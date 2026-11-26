# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, mute_logger, new_test_user, tagged

from odoo.addons.ai_oca_bridge_openwebui_web_editor.controllers.main import (
    HtmlEditorOpenWebUI,
)
from odoo.addons.html_editor.controllers.main import HTML_Editor


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

    def _call_route(self, prompt, history, env=None):
        request_proxy = SimpleNamespace(env=env or self.env)
        with (
            patch(
                "odoo.addons.ai_oca_bridge_openwebui_web_editor.controllers.main.request",
                request_proxy,
            ),
            patch(
                "odoo.addons.ai_oca_bridge_openwebui_web_editor.controllers.main._",
                side_effect=lambda source, *args, **kwargs: source,
            ),
            patch(
                "odoo.addons.ai_oca_bridge_openwebui.models.openwebui_client._",
                side_effect=lambda source, *args, **kwargs: source,
            ),
        ):
            return HtmlEditorOpenWebUI.generate_text.__wrapped__(
                HtmlEditorOpenWebUI(), prompt, history
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
            result = HtmlEditorOpenWebUI.generate_text.__wrapped__(
                HtmlEditorOpenWebUI(),
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

    def test_no_editor_bridge_preserves_parent_provider(self):
        self.bridge.active = False
        request_proxy = SimpleNamespace(env=self.env)
        with (
            patch(
                "odoo.addons.ai_oca_bridge_openwebui_web_editor.controllers.main.request",
                request_proxy,
            ),
            patch.object(
                HTML_Editor, "generate_text", return_value="parent-provider"
            ) as parent,
        ):
            result = HtmlEditorOpenWebUI.generate_text.__wrapped__(
                HtmlEditorOpenWebUI(), "Draft text", []
            )
        self.assertEqual(result, "parent-provider")
        parent.assert_called_once_with("Draft text", [])

    def test_invalid_prompt_and_conversation_are_rejected(self):
        for prompt in ("  ", 3):
            with self.assertRaises(UserError):
                self._call_route(prompt, [])
        for history in (
            None,
            [{"role": "tool", "content": "unsupported"}],
            [{"role": "user", "content": 5}],
            [{"role": "user", "content": "x"}] * 41,
            [{"role": "system", "content": "x" * 100_001}],
        ):
            with self.assertRaises(UserError):
                self._call_route("Write", history)

    def test_non_internal_users_cannot_use_editor_generation(self):
        portal_user = new_test_user(
            self.env, login="web-editor-portal", groups="base.group_portal"
        )
        with self.assertRaises(AccessError):
            self._call_route("Write", [], env=self.env(user=portal_user))

    def test_ambiguous_group_or_model_configuration_is_rejected(self):
        second_bridge = self.bridge.copy({"name": "Second HTML Editor bridge"})
        with self.assertRaisesRegex(UserError, "exactly one active"):
            self._call_route("Write", [])
        second_bridge.unlink()

        restricted_group = self.env["res.groups"].create({"name": "HTML AI restricted"})
        self.bridge.group_ids = [(6, 0, [restricted_group.id])]
        with self.assertRaises(AccessError):
            self._call_route("Write", [])
        self.bridge.group_ids = False

        partner_model = self.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )
        self.bridge.model_id = partner_model
        with self.assertRaisesRegex(UserError, "must not be restricted"):
            self._call_route("Write", [])

    @mute_logger("odoo.addons.ai_oca_bridge_openwebui.models.openwebui_client")
    def test_openwebui_failure_is_not_sent_to_parent_provider(self):
        with patch(
            "requests.request", side_effect=requests.ConnectionError("unavailable")
        ):
            with self.assertRaisesRegex(UserError, "could not generate a response"):
                self._call_route("Write", [])
