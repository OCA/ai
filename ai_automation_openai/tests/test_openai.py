# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)

from odoo.tests.common import TransactionCase


class OpenAIClient:
    def __init__(self, chat_messages=None):
        self.chat_messages = chat_messages or []
        self.current_message = -1
        self.calls = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, *args, **kwargs):  # pylint: disable=W8106
        self.current_message += 1
        self.calls.append((args, kwargs))
        return ChatCompletion(
            id="chatcmpl-123",
            object="chat.completion",
            created=1677652288,
            model="gpt-3.5-turbo-0301",
            choices=[
                Choice(
                    index=0,
                    logprobs=None,
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        id=self.current_message,
                        **self.chat_messages[self.current_message]
                    ),
                )
            ],
        )


class TestOpenai(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env["ai.connection"].create(
            {
                "name": "My Connection",
                "url": "http://my_service:11434",
                "model": "my_openai_model",
                "kind": "openai",
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
        client = OpenAIClient(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        ChatCompletionMessageToolCall(
                            id="1",
                            type="function",
                            function=Function(
                                name="get_date",
                                arguments="{}",  # must be a JSON string, not a dict
                            ),
                        )
                    ],
                },
                {
                    "role": "assistant",
                    "content": "Thanks it is 2024-01-01",
                },
            ]
        )
        with mock.patch("openai.OpenAI", return_value=client):
            messages = self.partner.message_ids
            self.action.with_context(
                active_id=self.partner.id, active_model="res.partner"
            ).run()
            self.assertEqual(client.current_message, 1)
            self.assertEqual(messages, self.partner.message_ids)
