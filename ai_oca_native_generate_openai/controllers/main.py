# Copyright 2026 Nitrokey GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import openai

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.html_editor.controllers.main import HTML_Editor

_logger = logging.getLogger(__name__)


class HTMLEditorOpenAI(HTML_Editor):
    @http.route()
    def generate_text(self, prompt, conversation_history):
        ICP = request.env["ir.config_parameter"].sudo()
        url = ICP.get_param("ai_oca_native_generate_openai.url")
        model = ICP.get_param("ai_oca_native_generate_openai.model")
        if not url or not model:
            return super().generate_text(prompt, conversation_history)
        api_key = ICP.get_param("ai_oca_native_generate_openai.api_key")
        temperature = ICP.get_param("ai_oca_native_generate_openai.temperature")
        timeout = ICP.get_param("ai_oca_native_generate_openai.timeout", "60")
        # The client refuses to start without a key, even if the server
        # does not require one
        client = openai.OpenAI(
            base_url=url,
            api_key=api_key or "none",
            timeout=float(timeout),
        )
        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": prompt})
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=float(temperature) if temperature else openai.NOT_GIVEN,
            )
        except openai.OpenAIError as e:
            _logger.exception("Error while generating text")
            raise UserError(
                _("Sorry, we could not generate a response. Please try again later.")
            ) from e
        return response.choices[0].message.content
