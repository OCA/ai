# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.ai_oca_native_llm.tests.common import (
    OpenAIMockDecisionResponse,
    OpenAIMockResponse,
)


class TestAiLlmTool(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_get_date = cls.env.ref("ai_tool.current_date")
        cls.tool_post_message = cls.env.ref("ai_tool.post_message")
        cls.tools = cls.tool_get_date | cls.tool_post_message

    def test_get_openai_tools_definitions_converts_recordset(self):
        definitions = self.tools.get_openai_tools_definitions()
        self.assertEqual(len(definitions), 2)
        self.assertEqual(definitions[0]["type"], "function")
        self.assertEqual(definitions[0]["function"]["name"], "get_date")
        self.assertEqual(definitions[1]["function"]["name"], "post_message")
        self.assertIn("message", definitions[1]["function"]["parameters"]["properties"])

    def test_get_decision_tool_candidates_with_done(self):
        candidates = self.tools.get_decision_tool_candidates(include_done=True)
        self.assertEqual(
            [c["value"] for c in candidates],
            ["get_date", "post_message", "done"],
        )

    def test_get_decision_tool_candidates_without_done(self):
        candidates = self.tools.get_decision_tool_candidates(include_done=False)
        self.assertEqual(
            [c["value"] for c in candidates],
            ["get_date", "post_message"],
        )

    def test_requires_arguments_detects_schema_inputs(self):
        self.assertFalse(self.tool_get_date._requires_arguments())
        self.assertTrue(self.tool_post_message._requires_arguments())

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_accepts_ai_tool_recordset_directly(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_instance.chat.completions.create.return_value = OpenAIMockResponse(
            "Used tool schema", tool_calls=[]
        )

        result = self.env["ai.llm.client"].chat(
            [{"role": "user", "content": "What is today's date?"}],
            tools=self.tool_get_date,
        )

        call_kwargs = mock_instance.chat.completions.create.call_args.kwargs
        self.assertEqual(
            call_kwargs["tools"], self.tool_get_date.get_openai_tools_definitions()
        )
        self.assertEqual(
            result,
            {"content": "Used tool schema", "tool_calls": []},
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_decide_tool_routes_ai_tool_recordset(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        choice_ans = type(
            "MockChoiceAns",
            (),
            {
                "name": "next_action",
                "type": "choice",
                "choice": "get_date",
                "confidence": 0.96,
                "probabilities": [],
            },
        )()
        mock_instance.decisions.create.return_value = OpenAIMockDecisionResponse(
            answers=[choice_ans]
        )

        res = self.env["ai.llm.client"].decide_tool(
            input_data="What day is it?",
            tools=self.tools,
            instructions="Choose the best tool",
        )
        self.assertEqual(res["choice"], "get_date")
        sent_choices = mock_instance.decisions.create.call_args.kwargs["questions"][0][
            "choices"
        ]
        self.assertEqual(
            [c["value"] for c in sent_choices],
            ["get_date", "post_message", "done"],
        )
