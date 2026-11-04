# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MailMessageImportSender(models.Model):
    _inherit = "mail.message.import.sender"

    purchase_count = fields.Integer(compute="_compute_purchase_count")

    def _compute_purchase_count(self):
        Quote = self.env["ai.message.import.document"]
        for sender in self:
            sender.purchase_count = len(
                Quote.search(
                    [("sender_id", "=", sender.id), ("state", "!=", "cancelled")]
                ).purchase_order_id
            )

    def action_view_purchases(self):
        orders = (
            self.env["ai.message.import.document"]
            .search([("sender_id", "in", self.ids)])
            .purchase_order_id
        )
        return self._action_related("purchase.purchase_rfq", [("id", "in", orders.ids)])
