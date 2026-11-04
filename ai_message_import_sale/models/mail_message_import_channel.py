# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MailMessageImportChannel(models.Model):
    _inherit = "mail.message.import.channel"

    sale_count = fields.Integer(compute="_compute_sale_count")
    sale_to_confirm_count = fields.Integer(compute="_compute_sale_count")

    def _sale_orders(self):
        return (
            self.env["ai.message.import.document"]
            .search([("channel_id", "in", self.ids), ("state", "!=", "cancelled")])
            .sale_order_id
        )

    def _compute_sale_count(self):
        for channel in self:
            orders = channel._sale_orders()
            channel.sale_count = len(orders)
            # Counted for the panel, even without the rights on the orders.
            channel.sale_to_confirm_count = len(
                orders.sudo().filtered(lambda o: o.state in ("draft", "sent"))
            )

    def action_view_sales(self):
        orders = (
            self.env["ai.message.import.document"]
            .search([("channel_id", "in", self.ids)])
            .sale_order_id
        )
        return self._action_related(
            "sale.action_quotations_with_onboarding", [("id", "in", orders.ids)]
        )

    def action_view_sales_to_confirm(self):
        orders = self._sale_orders().filtered(lambda o: o.state in ("draft", "sent"))
        return self._action_related(
            "sale.action_quotations_with_onboarding", [("id", "in", orders.ids)]
        )
