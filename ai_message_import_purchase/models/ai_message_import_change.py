# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiMessageImportChange(models.Model):
    _inherit = "ai.message.import.change"

    purchase_order_id = fields.Many2one(
        "purchase.order", readonly=True, index=True, ondelete="cascade"
    )
    purchase_line_id = fields.Many2one(
        "purchase.order.line", string="Order line", readonly=True, ondelete="set null"
    )
