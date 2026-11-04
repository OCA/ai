# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MailMessageImportSender(models.Model):
    _inherit = "mail.message.import.sender"

    sale_count = fields.Integer(compute="_compute_sale_count")

    def _compute_sale_count(self):
        Quote = self.env["ai.message.import.document"]
        for sender in self:
            sender.sale_count = len(
                Quote.search(
                    [("sender_id", "=", sender.id), ("state", "!=", "cancelled")]
                ).sale_order_id
            )

    def action_view_sales(self):
        orders = (
            self.env["ai.message.import.document"]
            .search([("sender_id", "in", self.ids)])
            .sale_order_id
        )
        return self._action_related(
            "sale.action_quotations_with_onboarding", [("id", "in", orders.ids)]
        )
