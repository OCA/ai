# Copyright 2025 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_llm_base_url = fields.Char(
        string="LLM Base URL",
        config_parameter="ai_llm.base_url",
        default="http://localhost:11434/v1",
        help="The URL of the OpenAI compatible API server.",
    )
    ai_llm_api_key = fields.Char(
        string="API Key",
        config_parameter="ai_oca_native_llm.api_key",
        default="",
        help="The API provider's access key (can be dummy value for local instances).",
    )
    ai_llm_reasoning_model = fields.Char(
        string="Reasoning Model",
        config_parameter="ai_llm.reasoning_model",
        default="llama3",
        help="The model to use for complex AI reasoning (e.g., llama3, gpt-4o).",
    )
    ai_llm_fast_model = fields.Char(
        string="Fast Model",
        config_parameter="ai_llm.fast_model",
        default="llama3.2",
        help="The model to use for rapid extractions (e.g., llama3.2, gpt-4o-mini).",
    )
