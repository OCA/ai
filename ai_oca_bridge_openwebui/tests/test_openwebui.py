# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unittest
from unittest import mock

import requests

from odoo.exceptions import UserError, ValidationError
from odoo.tests import common, new_test_user
from odoo.tools import mute_logger

try:
    import markdown
except ImportError:
    markdown = None


def _completion(content="Hello, I am the assistant."):
    return mock.Mock(
        status_code=200,
        text="ok",
        json=lambda: {"choices": [{"message": {"content": content}}]},
    )


def _catalog_response(data):
    response = mock.Mock()
    response.json.return_value = data
    response.raise_for_status.return_value = None
    return response


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
        cls.chat = (
            cls.env["discuss.channel"]
            .with_user(cls.user.id)
            .create(
                {
                    "name": "Sales",
                    "channel_type": "chat",
                    "channel_member_ids": [
                        (0, 0, {"partner_id": cls.ai_user.partner_id.id}),
                        (0, 0, {"partner_id": cls.user.partner_id.id}),
                    ],
                }
            )
        )

    def _messages(self):
        return self.env["mail.message"].search(
            [("res_id", "=", self.chat.id), ("model", "=", "discuss.channel")]
        )

    def _create_message(self, model, res_id, body, message_type="comment"):
        return (
            self.env["mail.message"]
            .sudo()
            .create(
                {
                    "author_id": self.user.partner_id.id,
                    "body": body,
                    "model": model,
                    "res_id": res_id,
                    "message_type": message_type,
                    "subtype_id": self.env.ref("mail.mt_comment").id,
                    "partner_ids": [(6, 0, [self.ai_user.partner_id.id])],
                }
            )
        )

    def _execution_for_message(self, message):
        return (
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

    def _execute_message(self, message):
        execution = self._execution_for_message(message)
        execution._execute()
        return execution

    def _execute_chat_message(self, body):
        return self._execute_message(
            self._create_message("discuss.channel", self.chat.id, body)
        )

    def test_catalog_sync_models_and_tools(self):
        with mock.patch(
            "requests.get",
            side_effect=[
                _catalog_response({"data": [{"id": "model-a", "name": "Model A"}]}),
                _catalog_response(
                    [
                        {
                            "id": "tool-a",
                            "name": "Tool A",
                            "meta": {"description": "Description A"},
                        }
                    ]
                ),
            ],
        ) as request:
            self.bridge.action_openwebui_sync_catalog()
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            self.env["ai.openwebui.model"]
            .search([("external_id", "=", "model-a")])
            .name,
            "Model A",
        )
        tool = self.env["ai.openwebui.tool"].search([("external_id", "=", "tool-a")])
        self.assertEqual(tool.description, "Description A")

    def test_catalog_sync_updates_existing_records(self):
        model = self.env["ai.openwebui.model"].create(
            {"name": "Old", "external_id": "model-a"}
        )
        tool = self.env["ai.openwebui.tool"].create(
            {"name": "Old", "external_id": "tool-a"}
        )
        with mock.patch(
            "requests.get",
            side_effect=[
                _catalog_response({"data": [{"id": "model-a"}]}),
                _catalog_response([{"id": "tool-a", "name": "New", "meta": {}}]),
            ],
        ):
            self.bridge.action_openwebui_sync_catalog()
        self.assertEqual(model.name, "model-a")
        self.assertEqual(tool.name, "New")

    def test_catalog_sync_requires_url_and_token(self):
        self.bridge.url = False
        with self.assertRaises(UserError):
            self.bridge._openwebui_sync_endpoint("/api/models", "models")
        self.bridge.url = "https://openwebui.example.com/api/chat/completions"
        self.bridge.auth_token = False
        with self.assertRaises(UserError):
            self.bridge._openwebui_sync_endpoint("/api/models", "models")

    def test_catalog_tools_and_model_onchange(self):
        tool = self.env["ai.openwebui.tool"].create(
            {"name": "Tool", "external_id": "tool-a"}
        )
        self.bridge.openwebui_tool_record_ids = [(6, 0, tool.ids)]
        self.assertEqual(self.bridge._openwebui_tool_ids(), ["tool-a"])
        model = self.env["ai.openwebui.model"].create(
            {"name": "Model", "external_id": "model-a"}
        )
        self.bridge.openwebui_model_id = model
        self.bridge._onchange_openwebui_model_id()
        self.assertEqual(self.bridge.openwebui_model, "model-a")

    def test_bridge_onchange_and_validation(self):
        values = {
            "name": "Onchange",
            "payload_type": "openwebui",
            "usage": "chatter",
            "result_kind": "immediate",
            "result_type": "message",
        }
        bridge = self.env["ai.bridge"].new(values)
        bridge._onchange_payload_type_openwebui()
        self.assertEqual(bridge.result_kind, "immediate")
        invalid_values = [
            {"usage": "thread"},
            {"result_kind": "async"},
            {"result_type": "none"},
        ]
        for invalid in invalid_values:
            invalid_bridge = self.env["ai.bridge"].new({**values, **invalid})
            with self.assertRaises(ValidationError):
                invalid_bridge._check_openwebui_configuration()

    def test_bridge_requires_model_and_legacy_tools(self):
        self.bridge.openwebui_model = False
        self.bridge.openwebui_model_id = False
        with self.assertRaises(ValidationError):
            self.bridge._openwebui_check_model()
        self.bridge.openwebui_model = "demo-sales"
        self.bridge.openwebui_tool_ids = "tool-a, tool-b, ,tool-c"
        self.assertEqual(
            self.bridge._openwebui_tool_ids(), ["tool-a", "tool-b", "tool-c"]
        )

    def test_prepare_payload_without_record_and_with_tools(self):
        self._create_message("discuss.channel", self.chat.id, "Question")
        self.bridge.openwebui_tool_ids = "tool-a"
        payload = self.bridge._prepare_payload()
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertEqual(payload["tool_ids"], ["tool-a"])
        self.assertEqual(payload["params"], {"function_calling": "legacy"})

    def test_get_channel_rejects_invalid_messages(self):
        message = self._create_message(
            "res.partner", self.env.user.partner_id.id, "invalid"
        )
        message.model = False
        with self.assertRaises(ValueError):
            self._execution_for_message(message)._get_channel()
        message = self._create_message(
            "res.partner", self.env.user.partner_id.id, "invalid"
        )
        message.model = "missing.model"
        with self.assertRaises(ValueError):
            self._execution_for_message(message)._get_channel()
        partner = self.env["res.partner"].create({"name": "Deleted Target"})
        message = self._create_message("res.partner", partner.id, "invalid")
        message.res_id = 999999999
        with self.assertRaises(ValueError):
            self._execution_for_message(message)._get_channel()

    def test_execute_ignores_mismatch_and_non_comment(self):
        self.bridge.model_id = self.env["ir.model"]._get("res.partner")
        message = self._create_message("discuss.channel", self.chat.id, "Question")
        execution = self._execution_for_message(message)
        self.assertEqual(execution._execute(), {})
        self.assertEqual(execution.state, "done")
        message = self._create_message(
            "discuss.channel", self.chat.id, "Notification", "notification"
        )
        execution = self._execution_for_message(message)
        with mock.patch("requests.post") as request:
            execution._execute()
        request.assert_not_called()
        self.assertEqual(execution.state, "done")

    def test_execute_handles_http_error(self):
        response = _completion()
        response.raise_for_status.side_effect = requests.HTTPError("bad response")
        with mock.patch("requests.post", return_value=response):
            execution = self._execute_chat_message("Question")
        self.assertEqual(execution.state, "error")

    def test_stop_typing_without_context_or_for_other_model(self):
        self.env["ai.bridge.execution"].new(
            {"ai_bridge_id": self.bridge.id}
        )._openwebui_stop_typing()
        partner = self.env["res.partner"].create({"name": "Target"})
        message = self._create_message("res.partner", partner.id, "Question")
        self._execution_for_message(message)._openwebui_stop_typing()

    def test_malformed_openwebui_responses(self):
        execution = self.env["ai.bridge.execution"].new(
            {"ai_bridge_id": self.bridge.id}
        )
        for response in ({}, {"choices": []}, {"choices": [{}]}):
            with self.assertRaises(ValueError):
                execution._openwebui_to_message(response)

    def test_mail_thread_discuss_does_not_duplicate(self):
        with mock.patch("requests.post") as request:
            self.chat.with_user(self.user.id).message_post(body="Question")
        request.assert_not_called()

    def test_mail_thread_partner_creates_execution(self):
        partner = self.env["res.partner"].create({"name": "Target"})
        self.bridge.model_id = self.env["ir.model"]._get("res.partner")
        with mock.patch(
            "requests.post", return_value=_completion("Réponse")
        ) as request:
            partner.message_post(
                body="Question",
                message_type="comment",
                partner_ids=[self.ai_user.partner_id.id],
            )
        request.assert_called_once()

    def test_mail_thread_ignores_non_comment_and_disabled_bridge(self):
        partner = self.env["res.partner"].create({"name": "Target"})
        self.bridge.model_id = self.env["ir.model"]._get("res.partner")
        with mock.patch("requests.post") as request:
            partner.message_post(
                body="Notification",
                message_type="notification",
                partner_ids=[self.ai_user.partner_id.id],
            )
        request.assert_not_called()
        self.bridge.domain = '[("id", "=", 0)]'
        with mock.patch("requests.post") as request:
            partner.message_post(
                body="Question",
                message_type="comment",
                partner_ids=[self.ai_user.partner_id.id],
            )
        request.assert_not_called()

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
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        self.assertEqual(2, len(self._messages()))

    def test_res_partner_payload_uses_configured_model(self):
        self.bridge.model_id = self.env["ir.model"]._get("res.partner")
        partner = self.env["res.partner"].create({"name": "OpenWebUI Test Partner"})
        message = self._create_message("res.partner", partner.id, "Question")
        payload = self.bridge._prepare_payload(record=message)
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertIn("res.partner", payload["messages"][0]["content"])

    def test_res_partner_answer_is_posted(self):
        self.bridge.model_id = self.env["ir.model"]._get("res.partner")
        partner = self.env["res.partner"].create({"name": "OpenWebUI Test Partner"})
        message = self._create_message("res.partner", partner.id, "Question")
        with mock.patch(
            "requests.post", return_value=_completion("Réponse partenaire")
        ):
            execution = self._execute_message(message)
        self.assertEqual(execution.state, "done")
        self.assertTrue(
            partner.message_ids.filtered(lambda msg: "Réponse partenaire" in msg.body)
        )

    def test_history_roles(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = _completion("Answer 1")
            self._execute_chat_message("Question 1")
            mock_post.return_value = _completion("Answer 2")
            self._execute_chat_message("Question 2")
        self.assertEqual(
            [item["role"] for item in mock_post.call_args.kwargs["json"]["messages"]],
            ["system", "user", "assistant", "user"],
        )

    @mute_logger("odoo.addons.ai_oca_bridge_openwebui.models.ai_bridge_execution")
    def test_error_does_not_post(self):
        with mock.patch("requests.post", side_effect=Exception("boom")):
            execution = self._execute_chat_message("Question")
        self.assertEqual(execution.state, "error")

    @mute_logger("odoo.addons.ai_oca_bridge_openwebui.models.ai_bridge_execution")
    def test_empty_answer_is_an_error(self):
        with mock.patch("requests.post", return_value=_completion("   ")):
            execution = self._execute_chat_message("Question")
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
