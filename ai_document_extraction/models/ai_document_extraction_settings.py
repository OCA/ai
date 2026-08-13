# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AiDocumentExtractionSettings(models.TransientModel):
    _name = "ai.document.extraction.settings"
    _description = "AI Document Extraction Settings"

    ai_connection_id = fields.Many2one(
        "ai.connection",
        string="AI Connection",
        help="Connection used to extract invoice data from documents.",
    )
    fuzzy_match_threshold = fields.Integer(
        string="Partner Match Threshold",
        default=85,
        help="Minimum similarity percentage (0-100) required to auto-match the "
        "extracted partner name with an existing partner.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        param = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_document_extraction.ai_connection_id", "")
        )
        # Return False (not 0) when unset: a plain 0 on a many2one creates a
        # phantom record and crashes the settings onchange in Odoo 19.
        connection_id = False
        if param and param.isdigit():
            connection_id = int(param) or False
        res["ai_connection_id"] = connection_id
        res["fuzzy_match_threshold"] = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_document_extraction.fuzzy_match_threshold", "85")
        )
        return res

    def action_save(self):
        self.ensure_one()
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_document_extraction.ai_connection_id",
            str(self.ai_connection_id.id or 0),
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_document_extraction.fuzzy_match_threshold",
            str(self.fuzzy_match_threshold or 85),
        )
        return {"type": "ir.actions.act_window_close"}
