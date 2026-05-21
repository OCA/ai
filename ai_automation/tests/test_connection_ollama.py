# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from ollama._types import ChatResponse

from odoo.tests.common import TransactionCase


class OllamaClient:
    def __init__(self, chat_messages=None):
        self.chat_messages = chat_messages or []
        self.current_message = -1
        self.calls = []

    def chat(self, *args, **kwargs):
        self.current_message += 1
        self.calls.append((args, kwargs))
        return ChatResponse.model_validate(
            {"message": self.chat_messages[self.current_message]}
        )


class TestConnectionOllama(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env["ai.connection"].create(
            {
                "name": "Ollama Connection",
                "url": "http://my_ollama_server:11434",
                "model": "my_ollama_model",
                "kind": "ollama",
            }
        )
        cls.action = cls.env["ir.actions.server"].create(
            {
                "name": "Test Action",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "state": "ai_oca",
                "ai_connection_id": cls.connection.id,
                "ai_tool_ids": [(4, cls.env.ref("ai_tool.current_date").id)],
                "ai_prompt": "What is the current date?",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Test Partner"})

    def test_execute_action_with_tools(self):
        client = OllamaClient(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_date",
                                "arguments": {},
                            },
                            "id": "1",
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": "Thanks it is 2024-01-01",
                },
            ]
        )
        with mock.patch("ollama.Client", return_value=client):
            messages = self.partner.message_ids
            self.action.with_context(
                active_id=self.partner.id, active_model="res.partner"
            ).run()
            self.assertEqual(client.current_message, 1)
            self.assertEqual(messages, self.partner.message_ids)

    def test_execute_action_post_message(self):
        client = OllamaClient(
            [
                {
                    "role": "assistant",
                    "content": "Thanks it is 2024-01-01",
                },
            ]
        )
        self.action.ai_result_action = "post_message"
        with mock.patch("ollama.Client", return_value=client):
            messages = self.partner.message_ids
            self.action.with_context(
                active_id=self.partner.id, active_model="res.partner"
            ).run()
            self.assertEqual(client.current_message, 0)
            self.assertEqual(len(messages) + 1, len(self.partner.message_ids))
            self.assertRegex(
                (self.partner.message_ids - messages).body, r".*2024-01-01.*"
            )

    def test_execute_action_field(self):
        client = OllamaClient(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_date",
                                "arguments": {},
                            },
                            "id": "1",
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": "Thanks it is 2024-01-01",
                },
            ]
        )
        self.action.ai_result_action = "update_record"
        self.action.ai_update_record_field_id = self.env.ref(
            "base.field_res_partner__comment"
        )
        self.partner.comment = "Initial Comment"
        with mock.patch("ollama.Client", return_value=client):
            messages = self.partner.message_ids
            self.action.with_context(
                active_id=self.partner.id, active_model="res.partner"
            ).run()
            self.assertEqual(client.current_message, 1)
            self.assertEqual(messages, self.partner.message_ids)
            self.assertRegex(self.partner.comment, r".*2024-01-01.*")
