# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unittest
from unittest import mock

from odoo.exceptions import ValidationError
from odoo.tests import common, new_test_user

try:
    import markdown
except ImportError:
    markdown = None


def _completion(content="Hello, I am the assistant."):
    return mock.Mock(
        status_code=200,
        text="ok",
        json=lambda: {
            "choices": [{"message": {"role": "assistant", "content": content}}]
        },
    )


class TestOpenWebUI(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, mail_create_nosubscribe=True))
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "OpenWebUI Test",
                "url": "https://openwebui.example.com/api/chat/completions",
                "auth_type": "token",
                "auth_token": "sk-test",
                "usage": "chatter",
                "payload_type": "openwebui",
                "result_kind": "immediate",
                "result_type": "message",
                "openwebui_model": "demo-sales",
                "openwebui_system_prompt": "You are the project assistant.",
            }
        )
        cls.ai_user = new_test_user(
            cls.env, login="test-openwebui-ai", groups="base.group_user"
        )
        cls.ai_user.write({"ai_bridge_id": cls.bridge.id})
        cls.user = new_test_user(
            cls.env, login="test-openwebui-user", groups="base.group_user"
        )
        cls.chat = cls.env["discuss.channel"].create(
            {
                "name": "Sales",
                "channel_type": "chat",
                "channel_member_ids": [
                    (0, 0, {"partner_id": cls.ai_user.partner_id.id}),
                    (0, 0, {"partner_id": cls.user.partner_id.id}),
                ],
            }
        )

    def _messages(self):
        return self.env["mail.message"].search(
            [("res_id", "=", self.chat.id), ("model", "=", "discuss.channel")]
        )

    def _create_chat_message(self, body):
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
                    "partner_ids": [(6, 0, [self.ai_user.partner_id.id])],
                }
            )
        )

    def _execute_chat_message(self, body):
        message = self._create_chat_message(body)
        execution = (
            self.env["ai.bridge.execution"]
            .sudo()
            .create(
                {
                    "ai_bridge_id": self.bridge.id,
                    "model_id": self.env.ref("mail.model_mail_message").id,
                    "res_id": message.id,
                    "chatter_user_id": self.ai_user.id,
                }
            )
        )
        execution._execute()
        return execution

    def _create_partner_message(self, partner, body):
        return (
            self.env["mail.message"]
            .sudo()
            .create(
                {
                    "author_id": self.user.partner_id.id,
                    "body": body,
                    "model": "res.partner",
                    "res_id": partner.id,
                    "message_type": "comment",
                    "subtype_id": self.env.ref("mail.mt_comment").id,
                    "partner_ids": [(6, 0, [self.ai_user.partner_id.id])],
                }
            )
        )

    def test_answer_is_posted(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = _completion()
            execution = self._execute_chat_message("What is the delivery time?")
            mock_post.assert_called_once()
            payload = mock_post.call_args.kwargs["json"]
            headers = mock_post.call_args.kwargs["headers"]
        self.assertEqual(execution.state, "done")
        self.assertEqual(payload["model"], "demo-sales")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        self.assertEqual(2, len(self._messages()))
        answer = self._messages().sorted("id")[-1]
        self.assertEqual(answer.author_id, self.ai_user.partner_id)

    def test_res_partner_payload_uses_configured_model(self):
        self.bridge.model_id = self.env["ir.model"]._get("res.partner")
        partner = self.env["res.partner"].create({"name": "OpenWebUI Test Partner"})
        message = self._create_partner_message(partner, "Question dans le partenaire")
        payload = self.bridge._prepare_payload(record=message)
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertIn("Question dans le partenaire", payload["messages"][-1]["content"])
        self.assertIn("res.partner", payload["messages"][0]["content"])

    def test_res_partner_answer_is_posted(self):
        self.bridge.model_id = self.env["ir.model"]._get("res.partner")
        partner = self.env["res.partner"].create({"name": "OpenWebUI Test Partner"})
        message = self._create_partner_message(partner, "Question dans le partenaire")
        execution = (
            self.env["ai.bridge.execution"]
            .sudo()
            .create(
                {
                    "ai_bridge_id": self.bridge.id,
                    "model_id": self.env.ref("mail.model_mail_message").id,
                    "res_id": message.id,
                    "chatter_user_id": self.ai_user.id,
                }
            )
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = _completion("Réponse partenaire")
            execution._execute()
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(execution.state, "done")
        answer = partner.message_ids.sorted("id")[-1]
        self.assertEqual(answer.author_id, self.ai_user.partner_id)
        self.assertIn("Réponse partenaire", answer.body)

    def test_history_roles(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = _completion("Answer 1")
            self._execute_chat_message("Question 1")
            mock_post.return_value = _completion("Answer 2")
            self._execute_chat_message("Question 2")
            payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            [message["role"] for message in payload["messages"]],
            ["system", "user", "assistant", "user"],
        )

    def test_error_does_not_post(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("boom")
            execution = self._execute_chat_message("Question")
        self.assertEqual(1, len(self._messages()))
        self.assertEqual(execution.state, "error")

    def test_empty_answer_is_an_error(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = _completion("   ")
            execution = self._execute_chat_message("Question")
        self.assertEqual(1, len(self._messages()))
        self.assertEqual(execution.state, "error")

    @unittest.skipUnless(markdown, "Markdown is not installed")
    def test_markdown_response_is_converted_to_html(self):
        execution = self.env["ai.bridge.execution"].new(
            {"ai_bridge_id": self.bridge.id}
        )
        values = execution._openwebui_to_message(
            _completion("- **Module :** `web_gantt`").json()
        )
        self.assertIn("<strong>Module :</strong>", values["body"])
        self.assertIn("<code>web_gantt</code>", values["body"])

    def test_constraints(self):
        with self.assertRaises(ValidationError):
            self.bridge.result_kind = "async"

    def test_sample_payload(self):
        self.assertIn("demo-sales", self.bridge.sample_payload)
