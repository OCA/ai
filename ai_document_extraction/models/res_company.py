# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    ai_connection_id = fields.Many2one(
        "ai.connection",
        string="AI Document Extraction Connection",
    )
    ai_fuzzy_match_threshold = fields.Integer(
        string="AI Partner Match Threshold",
        default=85,
    )
