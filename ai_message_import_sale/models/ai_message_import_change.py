# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiMessageImportChange(models.Model):
    _inherit = "ai.message.import.change"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales quotation",
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Sales order line",
        readonly=True,
        ondelete="set null",
    )
