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
                "openwebui_keep_chat": True,
            }
        )
        cls.ai_user = new_test_user(
            cls.env,
            login="test-openwebui-ai",
            groups="base.group_user",
        )
        cls.ai_user.write({"ai_bridge_id": cls.bridge.id})
        cls.user = new_test_user(
            cls.env,
            login="test-openwebui-user",
            groups="base.group_user",
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

    def _execute_chat_message(self, body):
        execution = self._execution_for_message(
            self._create_message("discuss.channel", self.chat.id, body)
        )
        return execution._execute()

    def _agentic_request(self, calls, content="Hello, I am the assistant."):
        responses = {
            ("POST", "/api/v1/chats/new"): {"id": "chat-1"},
            ("POST", "/api/chat/completions"): {"status": True},
            ("GET", "/api/tasks/chat/chat-1"): {"task_ids": []},
            ("GET", "/api/v1/chats/chat-1"): {
                "chat": {
                    "history": {
                        "messages": {
                            "assistant-1": {
                                "role": "assistant",
                                "content": content,
                            }
                        }
                    }
                }
            },
        }

        def request(method, url, **kwargs):
            path = url.split(".com", 1)[-1]
            calls.append((method, path, kwargs))
            data = {} if method == "DELETE" else responses[(method, path)]
            response = mock.Mock(status_code=200, text="ack", json=lambda: data)
            response.raise_for_status.return_value = None
            response.close.return_value = None
            return response

        return request

    def _uuid_patch(self):
        return mock.patch(
            "odoo.addons.ai_oca_bridge_openwebui.models.ai_bridge_execution.uuid.uuid4",
            side_effect=["assistant-1", "user-1", "session-1"] * 10,
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
        self.assertEqual(
            self.env["ai.openwebui.tool"]
            .search([("external_id", "=", "tool-a")])
            .description,
            "Description A",
        )

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

    def test_prepare_payload_without_record_and_with_tools(self):
        self._create_message("discuss.channel", self.chat.id, "Question")
        self.bridge.openwebui_tool_ids = "tool-a"
        payload = self.bridge._prepare_payload()
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertEqual(payload["tool_ids"], ["tool-a"])
        self.assertEqual(payload["params"], {"function_calling": "legacy"})

    def test_agentic_answer_is_posted(self):
        calls = []
        with (
            mock.patch("requests.request", side_effect=self._agentic_request(calls)),
            self._uuid_patch(),
        ):
            result = self._execute_chat_message("What is the delivery time?")
        self.assertTrue(result)
        self.assertEqual(
            [call[:2] for call in calls][:4],
            [
                ("POST", "/api/v1/chats/new"),
                ("POST", "/api/chat/completions"),
                ("GET", "/api/tasks/chat/chat-1"),
                ("GET", "/api/v1/chats/chat-1"),
            ],
        )
        self.assertTrue(calls[1][2]["stream"])
        self.assertEqual(len(self._messages()), 2)

    def test_agentic_history_roles(self):
        calls = []
        with (
            mock.patch("requests.request", side_effect=self._agentic_request(calls)),
            self._uuid_patch(),
        ):
            self._execute_chat_message("Question 1")
            self._execute_chat_message("Question 2")
        self.assertEqual(calls[5][2]["json"]["messages"][-1]["role"], "user")

    def test_agentic_question_and_channel_title(self):
        calls = []
        with (
            mock.patch("requests.request", side_effect=self._agentic_request(calls)),
            self._uuid_patch(),
        ):
            self._execute_chat_message("Question visible in OpenWebUI")
        chat = calls[0][2]["json"]["chat"]
        self.assertEqual(chat["title"], self.chat.display_name)
        user = next(
            item
            for item in chat["history"]["messages"].values()
            if item["role"] == "user"
        )
        self.assertEqual(user["content"], "Question visible in OpenWebUI")

    def test_keep_chat_false_deletes_chat(self):
        self.bridge.openwebui_keep_chat = False
        calls = []
        with (
            mock.patch("requests.request", side_effect=self._agentic_request(calls)),
            self._uuid_patch(),
        ):
            self._execute_chat_message("Question")
        self.assertEqual(calls[-1][:2], ("DELETE", "/api/v1/chats/chat-1"))

    def test_get_channel_rejects_invalid_messages(self):
        message = self._create_message(
            "res.partner", self.env.user.partner_id.id, "invalid"
        )
        message.model = False
        with self.assertRaises(ValueError):
            self._execution_for_message(message)._get_channel()

    @mute_logger("odoo.addons.ai_oca_bridge_openwebui.models.ai_bridge_execution")
    def test_execute_handles_http_error(self):
        execution = self._execution_for_message(
            self._create_message("discuss.channel", self.chat.id, "Question")
        )
        with mock.patch(
            "odoo.addons.ai_oca_bridge_openwebui.models.ai_bridge_execution.AiBridgeExecution._openwebui_execute_agentic",
            side_effect=requests.ConnectionError("connection failed"),
        ):
            execution._execute()
        self.assertEqual(execution.state, "error")

    def test_mail_thread_discuss_does_not_duplicate(self):
        with mock.patch("requests.request") as request:
            self.chat.with_user(self.user.id).message_post(body="Question")
        request.assert_not_called()

    def test_malformed_openwebui_responses(self):
        execution = self.env["ai.bridge.execution"].new(
            {"ai_bridge_id": self.bridge.id}
        )
        for response in ({}, {"choices": []}, {"choices": [{}]}):
            with self.assertRaises(ValueError):
                execution._openwebui_to_message(response)

    @unittest.skipUnless(markdown, "Markdown is not installed")
    def test_markdown_response_is_converted_to_html(self):
        execution = self.env["ai.bridge.execution"].new(
            {"ai_bridge_id": self.bridge.id}
        )
        values = execution._openwebui_to_message(
            {"choices": [{"message": {"content": "- **Module :** `web_gantt`"}}]}
        )
        self.assertIn("<strong>Module :</strong>", values["body"])

    def test_constraints(self):
        with self.assertRaises(ValidationError):
            self.bridge.result_kind = "async"

    def test_sample_payload(self):
        self.assertIn("demo-sales", self.bridge.sample_payload)
