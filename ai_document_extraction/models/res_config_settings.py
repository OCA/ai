# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_api_base_url = fields.Char(
        string="AI API Base URL",
        default="http://ollama:11434/v1",
        config_parameter="ai_document_extraction.api_base_url",
    )
    ai_api_key = fields.Char(
        string="AI API Key",
        default="dummy",
        config_parameter="ai_document_extraction.api_key",
    )
    ai_model_name = fields.Char(
        string="AI Model Name",
        default="qwen3:4b",
        config_parameter="ai_document_extraction.model_name",
    )
    ocr_language = fields.Selection(
        [
            ("tur+eng", "Turkish + English"),
            ("tur", "Turkish"),
            ("eng", "English"),
        ],
        string="OCR Language",
        default="tur+eng",
        config_parameter="ai_document_extraction.ocr_language",
    )
    fuzzy_match_threshold = fields.Integer(
        string="Partner Match Threshold",
        default=85,
        help="Minimum similarity percentage (0-100) required to auto-match the "
        "extracted partner name with an existing partner.",
        config_parameter="ai_document_extraction.fuzzy_match_threshold",
    )
