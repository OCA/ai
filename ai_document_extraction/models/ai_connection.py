# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from ..services.ai_openai_compatible_client import AiOpenAICompatibleClient


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[("openai_compatible", "OpenAI-compatible")],
        ondelete={"openai_compatible": "cascade"},
    )
    api_key = fields.Char(groups="base.group_system")
    num_ctx = fields.Integer(
        string="Ollama Context Window",
        groups="base.group_system",
        help="Ollama num_ctx, only used when the URL points to an Ollama server.",
    )
    keep_alive = fields.Char(
        string="Ollama Keep Alive",
        groups="base.group_system",
        help="Ollama keep_alive duration, e.g. 30m.",
    )
    temperature = fields.Float(default=0.0)

    def _get_client_openai_compatible(self, tools):
        return AiOpenAICompatibleClient(
            url=self.url,
            model=self.model,
            api_key=self.api_key,
            num_ctx=self.num_ctx,
            keep_alive=self.keep_alive,
            timeout=int(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("ai_document_extraction.llm_timeout", "300")
            ),
        )
