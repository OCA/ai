from unittest.mock import patch

from odoo.orm.model_classes import add_to_registry
from odoo.tests.common import TransactionCase

from odoo.addons.ai_oca_native_llm.tests.common import (
    OpenAIMockDecisionResponse,
    OpenAIMockResponse,
)


class TestAiLlmClient(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from .fake_models import FakeModel

        add_to_registry(cls.registry, FakeModel)
        cls.addClassCleanup(cls.registry.__delitem__, "fake.model")
        cls.registry._setup_models__(cls.env.cr, ["fake.model"])
        cls.registry.init_models(cls.env.cr, ["fake.model"], {"models_to_check": True})
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_llm.base_url", "http://test-url:11434/v1"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_oca_native_llm.api_key", "test-key"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_llm.reasoning_model", "test-model"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_llm.fast_model", "other-model"
        )

    def setUp(self):
        super().setUp()

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_success(self, mock_client_class):
        # Mock the openai.OpenAI and its chat method
        mock_instance = mock_client_class.return_value
        mock_instance.chat.completions.create.return_value = OpenAIMockResponse(
            "Hello from mock"
        )

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(messages, options={"temperature": 0.7})

        # Assertions
        mock_client_class.assert_called_once_with(
            base_url="http://test-url:11434/v1", api_key="test-key"
        )
        mock_instance.chat.completions.create.assert_called_once_with(
            model="other-model",
            messages=messages,
            temperature=0.7,
        )
        self.assertEqual(response, "Hello from mock")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_success_with_specific_model_type(self, mock_client_class):
        # Mock the openai.OpenAI and its chat method
        mock_instance = mock_client_class.return_value
        mock_instance.chat.completions.create.return_value = OpenAIMockResponse(
            "Hello from mock"
        )

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(
            messages, model_type="reasoning", options={"temperature": 0.7}
        )

        # Assertions
        mock_client_class.assert_called_once_with(
            base_url="http://test-url:11434/v1", api_key="test-key"
        )
        mock_instance.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=messages,
            temperature=0.7,
        )
        self.assertEqual(response, "Hello from mock")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_success_with_explicit_model(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_instance.chat.completions.create.return_value = OpenAIMockResponse(
            "Hello from mock"
        )

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(
            messages, model="custom-llama", options={"temperature": 0.7}
        )

        # Assertions
        mock_instance.chat.completions.create.assert_called_once_with(
            model="custom-llama",
            messages=messages,
            temperature=0.7,
        )
        self.assertEqual(response, "Hello from mock")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_success_without_options(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_instance.chat.completions.create.return_value = OpenAIMockResponse(
            "Hello from mock without options"
        )

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(messages)

        # Assertions
        mock_instance.chat.completions.create.assert_called_once_with(
            model="other-model",
            messages=messages,
        )
        self.assertEqual(response, "Hello from mock without options")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_with_response_model(self, mock_client_class):
        from pydantic import BaseModel

        class MockModel(BaseModel):
            id: int

        mock_instance = mock_client_class.return_value
        mock_instance.beta.chat.completions.parse.return_value = OpenAIMockResponse(
            '{"id": 4}'
        )

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(
            messages, response_model=MockModel, options={"temperature": 0.7}
        )

        mock_instance.beta.chat.completions.parse.assert_called_once_with(
            model="other-model",
            messages=messages,
            response_format=MockModel,
            temperature=0.7,
        )
        self.assertEqual(response, '{"id": 4}')

    def test_get_model_fallback(self):
        # Clear the config parameters to test the fallback to default
        self.env["ir.config_parameter"].sudo().search(
            [("key", "in", ["ai_llm.fast_model", "ai_llm.reasoning_model"])]
        ).unlink()

        # Test default fallback for fast model
        fast_model = self.env["fake.model"]._get_model("fast")
        self.assertEqual(fast_model, "llama3.2")

        # Test default fallback for reasoning model
        reasoning_model = self.env["fake.model"]._get_model("reasoning")
        self.assertEqual(reasoning_model, "llama3")

        # Test default fallback for an unknown model type
        unknown_model = self.env["fake.model"]._get_model("unknown")
        self.assertEqual(unknown_model, "llama3.2")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_length_finish_reason_error(self, mock_client_class):
        from openai import LengthFinishReasonError

        mock_instance = mock_client_class.return_value
        mock_completion = OpenAIMockResponse("truncated content")
        mock_instance.beta.chat.completions.parse.side_effect = LengthFinishReasonError(
            completion=mock_completion
        )

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(messages, response_model=dict)
        self.assertIsNone(response)

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_api_error(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_instance.chat.completions.create.side_effect = Exception("API error")

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(messages)
        self.assertIsNone(response)

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_with_tools_no_calls(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_instance.chat.completions.create.return_value = OpenAIMockResponse(
            "Hello with tools", tool_calls=[]
        )

        messages = [{"role": "user", "content": "Hi"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        response = self.env["fake.model"].chat(
            messages, tools=tools, tool_choice="auto"
        )

        mock_instance.chat.completions.create.assert_called_once_with(
            model="other-model",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        self.assertEqual(
            response,
            {"content": "Hello with tools", "tool_calls": []},
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_chat_with_tools_and_tool_calls(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        fake_tool_call = type(
            "FakeToolCall",
            (),
            {
                "id": "call_123",
                "type": "function",
                "function": type(
                    "FakeFunction",
                    (),
                    {
                        "name": "agent_list_available_tools",
                        "arguments": '{"res_model": "sale.order"}',
                    },
                )(),
            },
        )()
        mock_instance.chat.completions.create.return_value = OpenAIMockResponse(
            None, tool_calls=[fake_tool_call]
        )

        messages = [{"role": "user", "content": "What tools exist?"}]
        tools = [
            {"type": "function", "function": {"name": "agent_list_available_tools"}}
        ]
        response = self.env["fake.model"].chat(messages, tools=tools)

        self.assertEqual(
            response,
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "agent_list_available_tools",
                            "arguments": '{"res_model": "sale.order"}',
                        },
                    }
                ],
            },
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_get_client_uses_model_type_specific_base_url_when_configured(
        self, mock_client_class
    ):
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_llm.decision_base_url", "http://decision-host:8001/v1"
        )
        self.env["fake.model"]._get_client(model_type="decision")
        mock_client_class.assert_called_once_with(
            base_url="http://decision-host:8001/v1", api_key="test-key"
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_decide_serializes_choice_predicate_score_and_refusal_answers(
        self, mock_client_class
    ):
        mock_instance = mock_client_class.return_value
        choice_ans = type(
            "MockChoiceAns",
            (),
            {
                "name": "q_choice",
                "type": "choice",
                "choice": "get_date",
                "confidence": 0.95,
                "probabilities": [
                    type(
                        "MockProb",
                        (),
                        {"value": "get_date", "probability": 0.95},
                    )(),
                    type(
                        "MockProb",
                        (),
                        {"value": "done", "probability": 0.05},
                    )(),
                ],
            },
        )()
        predicate_ans = type(
            "MockPredAns",
            (),
            {
                "name": "q_pred",
                "type": "predicate",
                "probability": 0.88,
            },
        )()
        score_ans = type(
            "MockScoreAns",
            (),
            {
                "name": "q_score",
                "type": "score",
                "score": 2.5,
                "confidence": 0.8,
                "probabilities": [
                    type(
                        "MockScoreProb",
                        (),
                        {"label": "high", "value": 3, "probability": 0.5},
                    )()
                ],
            },
        )()
        refusal_ans = type(
            "MockRefusalAns",
            (),
            {
                "name": "q_refusal",
                "type": "refusal",
            },
        )()
        mock_instance.decisions.create.return_value = OpenAIMockDecisionResponse(
            answers=[choice_ans, predicate_ans, score_ans, refusal_ans]
        )

        questions = [{"name": "q_choice", "type": "choice"}]
        res = self.env["fake.model"].decide(
            input_data="Test input",
            questions=questions,
            options={"safety_identifier": "org-1"},
        )

        mock_instance.decisions.create.assert_called_once_with(
            model="decision",
            input="Test input",
            questions=questions,
            safety_identifier="org-1",
        )
        self.assertEqual(len(res), 4)
        self.assertEqual(res[0]["choice"], "get_date")
        self.assertEqual(res[0]["confidence"], 0.95)
        self.assertEqual(len(res[0]["probabilities"]), 2)
        self.assertEqual(res[1], {"name": "q_pred", "type": "predicate", "probability": 0.88})
        self.assertEqual(res[2]["type"], "score")
        self.assertEqual(res[2]["score"], 2.5)
        self.assertEqual(res[2]["probabilities"][0]["label"], "high")
        self.assertEqual(res[3], {"name": "q_refusal", "type": "refusal"})

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_decide_with_explicit_model_and_error_returns_none(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_instance.decisions.create.side_effect = RuntimeError("Decision failure")

        res = self.env["fake.model"].decide(
            input_data="Test",
            questions=[{"name": "q1", "type": "predicate", "instructions": "Check"}],
            model="custom-decision-model",
        )
        self.assertIsNone(res)

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_decide_choice_returns_choice_dict_or_none_on_refusal_or_error(
        self, mock_client_class
    ):
        mock_instance = mock_client_class.return_value
        choice_ans = type(
            "MockChoiceAns",
            (),
            {
                "name": "next_action",
                "type": "choice",
                "choice": "done",
                "confidence": 0.99,
                "probabilities": [],
            },
        )()
        refusal_ans = type(
            "MockRefusalAns",
            (),
            {
                "name": "next_action",
                "type": "refusal",
            },
        )()
        mock_instance.decisions.create.side_effect = [
            OpenAIMockDecisionResponse(answers=[choice_ans]),
            OpenAIMockDecisionResponse(answers=[refusal_ans]),
            RuntimeError("Network error"),
        ]

        choices = [
            {"value": "get_date", "description": "Get date"},
            {"value": "done", "description": "Finish"},
        ]
        ans1 = self.env["fake.model"].decide_choice(
            input_data="Hi",
            choices=choices,
            instructions="Pick next action",
        )
        self.assertEqual(ans1["choice"], "done")

        ans2 = self.env["fake.model"].decide_choice(
            input_data="Hi",
            choices=choices,
            instructions="Pick next action",
        )
        self.assertIsNone(ans2)

        ans3 = self.env["fake.model"].decide_choice(
            input_data="Hi",
            choices=choices,
            instructions="Pick next action",
        )
        self.assertIsNone(ans3)
