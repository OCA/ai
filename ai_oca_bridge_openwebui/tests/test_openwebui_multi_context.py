# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import common


class TestOpenWebUIMultiContext(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "OpenWebUI multi-context test",
                "url": "https://openwebui.example.com/api/chat/completions",
                "auth_type": "token",
                "auth_token": "sk-test",
                "usage": "chatter",
                "payload_type": "openwebui",
                "result_kind": "immediate",
                "result_type": "message",
                "openwebui_model": "demo",
            }
        )

    def test_bridge_without_model_is_available_for_multiple_chatter_models(self):
        self.assertFalse(self.bridge.model_id)
        discuss_message = self.env["mail.message"].new(
            {"model": "discuss.channel", "res_id": 1, "message_type": "comment"}
        )
        task_message = self.env["mail.message"].new(
            {"model": "project.task", "res_id": 1, "message_type": "comment"}
        )
        self.assertTrue(self.bridge._openwebui_target_matches(discuss_message))
        self.assertTrue(self.bridge._openwebui_target_matches(task_message))

    def test_bridge_model_restriction_remains_available(self):
        model = self.env["ir.model"].search([("model", "=", "project.task")], limit=1)
        if not model:
            self.skipTest("project is not installed")
        self.bridge.model_id = model
        discuss_message = self.env["mail.message"].new(
            {"model": "discuss.channel", "res_id": 1, "message_type": "comment"}
        )
        task_message = self.env["mail.message"].new(
            {"model": "project.task", "res_id": 1, "message_type": "comment"}
        )
        self.assertFalse(self.bridge._openwebui_target_matches(discuss_message))
        self.assertTrue(self.bridge._openwebui_target_matches(task_message))
