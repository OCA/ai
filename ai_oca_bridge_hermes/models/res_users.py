# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    hermes_gateway_ids = fields.Many2many(
        "hermes.gateway",
        string="Hermes Gateways",
        help="Hermes gateways this user is linked to.",
    )
