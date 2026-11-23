# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo.tests import common, new_test_user


class TestOpenWebUIFeatures(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, mail_create_nosubscribe=True))
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "OpenWebUI Features Test",
                "url": "https://openwebui.example.com/api/chat/completions",
                "auth_type": "token",
                "auth_token": "sk-test",
                "usage": "chatter",
                "payload_type": "openwebui",
                "result_kind": "immediate",
                "result_type": "message",
                "openwebui_model": "demo-vision",
                "openwebui_history_limit": 5,
            }
        )
        cls.user = new_test_user(
            cls.env, login="openwebui-feature-user", groups="base.group_user"
        )
        cls.ai_user = new_test_user(
            cls.env, login="openwebui-feature-ai", groups="base.group_user"
        )
        cls.ai_user.write({"ai_bridge_id": cls.bridge.id})
        cls.chat = cls.env["discuss.channel"].with_user(cls.user.id).create(
            {
                "name": "Feature chat",
                "channel_type": "chat",
                "channel_member_ids": [
                    (0, 0, {"partner_id": cls.user.partner_id.id}),
                    (0, 0, {"partner_id": cls.ai_user.partner_id.id}),
                ],
            }
        )

    def _message(self, body, author=None, attachments=None):
        values = {
            "author_id": (author or self.user).partner_id.id,
            "body": body,
            "model": "discuss.channel",
            "res_id": self.chat.id,
            "message_type": "comment",
            "subtype_id": self.env.ref("mail.mt_comment").id,
        }
        if attachments:
            values["attachment_ids"] = [(6, 0, attachments.ids)]
        return self.env["mail.message"].sudo().create(values)

    def test_image_is_embedded_as_openai_multimodal_content(self):
        raw = b"image bytes"
        attachment = self.env["ir.attachment"].create(
            {
                "name": "photo.png",
                "type": "binary",
                "datas": base64.b64encode(raw),
                "mimetype": "image/png",
            }
        )
        message = self._message("Que montre cette image ?", attachments=attachment)
        payload = self.bridge._prepare_payload(record=message)
        content = payload["messages"][-1]["content"]
        self.assertEqual(content[0]["text"], "Que montre cette image ?")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(
            content[1]["image_url"]["url"],
            "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
        )

    def test_history_is_limited_to_five_user_exchanges(self):
        for index in range(1, 7):
            self._message(f"Question {index}")
            self._message(f"Réponse {index}", author=self.ai_user)
        current = self._message("Question actuelle")
        payload = self.bridge._prepare_payload(record=current)
        contents = [
            item["content"]
            for item in payload["messages"]
            if item["role"] != "system"
        ]
        self.assertEqual(len(contents), 11)
        for index in range(2, 7):
            self.assertIn(f"Question {index}", contents[(index - 2) * 2])
            self.assertIn(f"Réponse {index}", contents[(index - 2) * 2 + 1])
            self.assertIn("Odoo chatter note | id=", contents[(index - 2) * 2])
            self.assertIn("date=", contents[(index - 2) * 2])
            self.assertIn("author=", contents[(index - 2) * 2])
        self.assertEqual(contents[-1], "Question actuelle")

    def test_record_context_contains_task_description_and_identity(self):
        if "project.task" not in self.env:
            self.skipTest("project is not installed")
        task = self.env["project.task"].create(
            {"name": "Context task", "description": "<p>Current task description</p>"}
        )
        message = self.env["mail.message"].sudo().create(
            {
                "author_id": self.user.partner_id.id,
                "body": "Question",
                "model": "project.task",
                "res_id": task.id,
                "message_type": "comment",
                "subtype_id": self.env.ref("mail.mt_comment").id,
            }
        )
        system = self.bridge._openwebui_system_content(message)
        self.assertIn("Model: project.task", system)
        self.assertIn(f"ID: {task.id}", system)
        self.assertIn("Name: Context task", system)
        self.assertIn("Description: Current task description", system)
