# Copyright 2025 Pierre Verkest
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_llm_ollama_url = fields.Char(
        string="Ollama URL",
        config_parameter="ai_llm.ollama_url",
        default="http://localhost:11434",
        help="The URL of the Ollama server.",
    )
    ai_llm_ollama_model = fields.Char(
        string="Ollama Model",
        config_parameter="ai_llm.ollama_model",
        default="llama3",
        help="The model to use for the AI features (e.g., llama3, mistral).",
    )
