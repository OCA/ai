# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_connection_id = fields.Many2one(
        related="company_id.ai_connection_id",
        readonly=False,
    )
    ai_fuzzy_match_threshold = fields.Integer(
        related="company_id.ai_fuzzy_match_threshold",
        readonly=False,
    )
