# Copyright 2025 Pierre Verkest
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)
import logging

from ollama import Client

from odoo import api, models

_logger = logging.getLogger(__name__)


class AiLlmClient(models.AbstractModel):
    """
    Abstract model to provide a simple Python client for Ollama.
    It resolves configuration dynamically and performs the HTTP calls.
    """

    _name = "ai.llm.client"
    _description = "AI LLM Client Wrapper"

    @api.model
    def _get_client(self):
        url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_llm.ollama_url", "http://localhost:11434")
        )
        return Client(host=url)

    @api.model
    def chat(self, messages, model=None, options=None):
        """
        Sends a chat request to Ollama.
        :param messages: list of dicts [{'role': 'user', 'content': 'hello'}, ...]
        :param options: dict of optional parameters (e.g. temperature)
        :return: dict response from Ollama
        """
        client = self._get_client()
        if not model:
            model = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("ai_llm.ollama_model", "llama3")
            )

        response = client.chat(
            model=model, messages=messages, options=options, stream=False
        )
        return response.message.content
