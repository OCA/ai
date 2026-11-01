from unittest.mock import patch

from odoo.orm.model_classes import add_to_registry
from odoo.tests.common import TransactionCase

from odoo.addons.ai_oca_native_llm.tests.common import OpenAIMockResponse


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
