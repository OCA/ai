# Copyright 2025 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from openai import LengthFinishReasonError, OpenAI

from odoo import api, models

_logger = logging.getLogger(__name__)


class AiLlmClient(models.AbstractModel):
    """
    Abstract model to provide a simple Python client setup for an Open LLM connection.
    It resolves configuration dynamically and performs the completions calls.
    """

    _name = "ai.llm.client"
    _description = "AI LLM Client Wrapper"

    @api.model
    def _get_client(self):
        url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_llm.base_url", "http://localhost:11434/v1")
        )
        api_key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_oca_native_llm.api_key")
        )
        return OpenAI(base_url=url, api_key=api_key)

    @api.model
    def _get_default_models_type(self):
        return {
            "fast": "llama3.2",
            "reasoning": "llama3",
        }

    @api.model
    def _get_model(self, model_type: str):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                f"ai_llm.{model_type}_model",
                self._get_default_models_type().get(model_type, "llama3.2"),
            )
        )

    @api.model
    def chat(
        self,
        messages,
        model_type="fast",
        model: str = None,
        options=None,
        response_model=None,
    ):
        """
        Sends a chat request via OpenAI-compatible endpoint.
        :param messages: list of dicts [{'role': 'user', 'content': 'hello'}, ...]
        :param model_type: 'reasoning' or 'fast'
        :param model: LLM model to use.
        :param options: dict of optional parameters (e.g. temperature, response_format)
        :param response_model: optional Pydantic Base Model class to parse
               the response into
        :return: string response content from the LLM, or None if request fails
        """
        client = self._get_client()
        if not model:
            model = self._get_model(model_type)

        if not options:
            options = {}

        try:
            _logger.info("LLM context and question: %s", messages)
            if response_model:
                response = client.beta.chat.completions.parse(
                    model=model,
                    messages=messages,
                    response_format=response_model,
                    **options,
                )
            else:
                response = client.chat.completions.create(
                    model=model, messages=messages, **options
                )
            _logger.info("LLM Response: %s", response.choices[0].message.content)
            return response.choices[0].message.content
        except LengthFinishReasonError as err:
            _logger.warning(
                "LLM completion truncated (context length limit reached): %s", err
            )
            return None
        except Exception as err:
            _logger.exception("LLM API completion failed: %s", err)
            return None
