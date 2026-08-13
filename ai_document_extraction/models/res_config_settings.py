# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

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
        config_parameter="ai_document_extraction.fuzzy_match_threshold",
    )

    def get_values(self):
        res = super().get_values()
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
        return res

    def set_values(self):
        result = super().set_values()
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_document_extraction.ai_connection_id",
            str(self.ai_connection_id.id or 0),
        )
        return result
