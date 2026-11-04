# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MailMessageImportIncident(models.Model):
    _inherit = "mail.message.import.incident"

    purchase_order_id = fields.Many2one(
        "purchase.order", readonly=True, index=True, ondelete="set null"
    )
    purchase_line_id = fields.Many2one(
        "purchase.order.line", string="Order line", readonly=True, ondelete="set null"
    )

    def _get_order(self):
        return self.purchase_order_id or super()._get_order()
