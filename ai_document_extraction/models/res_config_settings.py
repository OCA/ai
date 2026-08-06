# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_api_base_url = fields.Char(
        string="AI API Base URL",
        default="https://openrouter.ai/api/v1",
        config_parameter="ai_document_extraction.api_base_url",
    )
    ai_api_key = fields.Char(
        string="AI API Key",
        default="",
        config_parameter="ai_document_extraction.api_key",
    )
    ai_model_name = fields.Char(
        string="AI Model Name",
        default="qwen/qwen3-vl-32b-instruct",
        config_parameter="ai_document_extraction.model_name",
    )
    fuzzy_match_threshold = fields.Integer(
        string="Partner Match Threshold",
        default=85,
        help="Minimum similarity percentage (0-100) required to auto-match the "
        "extracted partner name with an existing partner.",
        config_parameter="ai_document_extraction.fuzzy_match_threshold",
    )
