from unittest.mock import patch

from odoo.orm.model_classes import add_to_registry
from odoo.tests.common import TransactionCase

from odoo.addons.ai_oca_native_llm.tests.common import OllamaMockResponse


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
            "ai_llm.ollama_url", "http://test-url:11434"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_llm.ollama_model", "test-model"
        )

    def setUp(self):
        super().setUp()

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.Client")
    def test_chat_success(self, mock_client_class):
        # Mock the ollama.Client and its chat method
        mock_instance = mock_client_class.return_value
        mock_instance.chat.return_value = OllamaMockResponse("Hello from mock")

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(messages, options={"temperature": 0.7})

        # Assertions
        mock_client_class.assert_called_once_with(host="http://test-url:11434")
        mock_instance.chat.assert_called_once_with(
            model="test-model",
            messages=messages,
            options={"temperature": 0.7},
            stream=False,
        )
        self.assertEqual(response, "Hello from mock")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.Client")
    def test_chat_success_whit_specific_model(self, mock_client_class):
        # Mock the ollama.Client and its chat method
        mock_instance = mock_client_class.return_value
        mock_instance.chat.return_value = OllamaMockResponse("Hello from mock")

        messages = [{"role": "user", "content": "Hi"}]
        response = self.env["fake.model"].chat(
            messages, model="other-model", options={"temperature": 0.7}
        )

        # Assertions
        mock_client_class.assert_called_once_with(host="http://test-url:11434")
        mock_instance.chat.assert_called_once_with(
            model="other-model",
            messages=messages,
            options={"temperature": 0.7},
            stream=False,
        )
        self.assertEqual(response, "Hello from mock")
