# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MailMessageImportChannel(models.Model):
    _inherit = "mail.message.import.channel"

    purchase_count = fields.Integer(compute="_compute_purchase_count")
    purchase_to_confirm_count = fields.Integer(compute="_compute_purchase_count")

    def _purchase_orders(self):
        return (
            self.env["ai.message.import.document"]
            .search([("channel_id", "in", self.ids), ("state", "!=", "cancelled")])
            .purchase_order_id
        )

    def _compute_purchase_count(self):
        for channel in self:
            orders = channel._purchase_orders()
            channel.purchase_count = len(orders)
            # Counted for the panel, even without the rights on the orders.
            channel.purchase_to_confirm_count = len(
                orders.sudo().filtered(lambda o: o.state in ("draft", "sent"))
            )

    def action_view_purchases(self):
        orders = (
            self.env["ai.message.import.document"]
            .search([("channel_id", "in", self.ids)])
            .purchase_order_id
        )
        return self._action_related("purchase.purchase_rfq", [("id", "in", orders.ids)])

    def action_view_purchases_to_confirm(self):
        orders = self._purchase_orders().filtered(
            lambda o: o.state in ("draft", "sent")
        )
        return self._action_related("purchase.purchase_rfq", [("id", "in", orders.ids)])
