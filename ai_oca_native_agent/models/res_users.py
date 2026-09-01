# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    is_ai_agent = fields.Boolean(
        "Is AI Agent",
        default=False,
        help="Technical flag marking dedicated AI service account users.",
    )
