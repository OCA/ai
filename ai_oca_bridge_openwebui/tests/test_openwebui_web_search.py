# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import common


class TestOpenWebUIWebSearch(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Web search test",
                "url": "https://openwebui.example.com/api/chat/completions",
                "auth_type": "token",
                "auth_token": "sk-test",
                "usage": "chatter",
                "payload_type": "openwebui",
                "result_kind": "immediate",
                "result_type": "message",
                "openwebui_model": "demo",
                "openwebui_web_search": True,
            }
        )

    def test_web_search_feature_is_sent(self):
        payload = self.bridge._prepare_payload()
        self.assertEqual(payload["features"], {"web_search": True})

    def test_odoo_reference_is_marked_as_internal_context(self):
        partner = self.env["res.partner"].create({"name": "Context partner"})
        message = self.env["mail.message"].create(
            {
                "body": "Question",
                "model": "res.partner",
                "res_id": partner.id,
                "message_type": "comment",
            }
        )
        content = self.bridge._openwebui_system_content(message)
        self.assertIn("not sources", content)
        self.assertIn("res.partner", content)

    def test_response_with_text_tool_result_is_supported(self):
        execution = self.env["ai.bridge.execution"].new(
            {"ai_bridge_id": self.bridge.id}
        )
        values = execution._openwebui_to_message(
            {
                "choices": [
                    {"message": {"content": [{"type": "text", "text": "Answer"}]}}
                ]
            }
        )
        self.assertIn("Answer", values["body"])
