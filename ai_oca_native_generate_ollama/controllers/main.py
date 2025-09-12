# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from ollama import Client

from odoo import http
from odoo.http import request
from odoo.tools.safe_eval import safe_eval

from odoo.addons.html_editor.controllers.main import HTML_Editor


class HTMLEditorOllama(HTML_Editor):
    @http.route()
    def generate_text(self, prompt, conversation_history):
        connection = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_oca_native_generate_ollama.connection")
        )
        model = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_oca_native_generate_ollama.model")
        )
        if not connection or not model:
            return super().generate_text(prompt, conversation_history)
        headers = safe_eval(
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_oca_native_generate_ollama.headers", "{}")
        )
        client = Client(
            host=connection,
            headers=headers,
        )
        messages = conversation_history.copy()
        messages.append({"role": "user", "content": prompt})
        response = client.chat(model=model, messages=messages)
        return response.message.content
