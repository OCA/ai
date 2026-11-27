# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_sale_matcher_connection_id = fields.Many2one(
        related="company_id.ai_sale_matcher_connection_id",
        readonly=False,
    )
