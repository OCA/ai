# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo import fields
from odoo.tests import common, new_test_user


class TestOpenWebuiAttachments(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, mail_create_nosubscribe=True))
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "OpenWebUI Attachments Test",
                "url": "https://openwebui.example.com/api/chat/completions",
                "auth_type": "token",
                "auth_token": "sk-test",
                "usage": "chatter",
                "payload_type": "openwebui",
                "result_kind": "immediate",
                "result_type": "message",
                "openwebui_model": "demo-sales",
            }
        )
        cls.ai_user = new_test_user(
            cls.env, login="test-openwebui-attachments-ai", groups="base.group_user"
        )
        cls.ai_user.write({"ai_bridge_id": cls.bridge.id})
        cls.user = new_test_user(
            cls.env, login="test-openwebui-attachments-user", groups="base.group_user"
        )
        cls.chat = (
            cls.env["discuss.channel"]
            .with_user(cls.user.id)
            .create(
                {
                    "name": "Attachments",
                    "channel_type": "chat",
                    "channel_member_ids": [
                        (0, 0, {"partner_id": cls.ai_user.partner_id.id}),
                        (0, 0, {"partner_id": cls.user.partner_id.id}),
                    ],
                }
            )
        )

    def _message(self, body="Question"):
        return (
            self.env["mail.message"]
            .sudo()
            .create(
                {
                    "author_id": self.user.partner_id.id,
                    "body": body,
                    "model": "discuss.channel",
                    "res_id": self.chat.id,
                    "message_type": "comment",
                    "subtype_id": self.env.ref("mail.mt_comment").id,
                }
            )
        )

    def _attachment(self, message, name, mimetype, data):
        attachment = self.env["ir.attachment"].create(
            {
                "name": name,
                "type": "binary",
                "datas": base64.b64encode(data) if data is not False else False,
                "mimetype": mimetype,
                "res_model": "mail.message",
                "res_id": message.id,
            }
        )
        message.attachment_ids = [(4, attachment.id)]
        return attachment

    def test_image_attachment_is_encoded_in_message_content(self):
        message = self._message()
        image = self._attachment(message, "image.png", "image/png", b"image-data")
        content = self.bridge._openwebui_message_content(message)
        self.assertEqual(content[0], {"type": "text", "text": "Question"})
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(
            content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        )
        self.assertIn(image, message.attachment_ids)

    def test_non_image_and_empty_image_attachments_are_ignored(self):
        message = self._message()
        self._attachment(message, "document.txt", "text/plain", b"text")
        self._attachment(message, "empty.png", "image/png", False)
        self.assertEqual(self.bridge._openwebui_message_content(message), "Question")

    def test_discuss_attachments_are_found_between_messages(self):
        previous = self._message("Previous")
        attachment = self.env["ir.attachment"].create(
            {
                "name": "channel-image.png",
                "type": "binary",
                "datas": base64.b64encode(b"channel-image"),
                "mimetype": "image/png",
                "res_model": "discuss.channel",
                "res_id": self.chat.id,
            }
        )
        attachment.write(
            {"create_date": fields.Datetime.add(previous.create_date, minutes=1)}
        )
        message = self._message("Current")
        message.write(
            {"create_date": fields.Datetime.add(attachment.create_date, minutes=1)}
        )
        attachments = self.bridge._openwebui_message_attachments(message)
        self.assertIn(attachment, attachments)
        self.assertTrue(previous.id < message.id)
