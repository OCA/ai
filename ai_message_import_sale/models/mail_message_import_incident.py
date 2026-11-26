# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MailMessageImportIncident(models.Model):
    _inherit = "mail.message.import.incident"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales quotation",
        readonly=True,
        index=True,
        ondelete="set null",
    )
    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Sales order line",
        readonly=True,
        ondelete="set null",
    )

    def _get_order(self):
        return self.sale_order_id or super()._get_order()
