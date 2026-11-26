# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from odoo.addons.ai_message_import.models.ai_message_import_order_mixin import (
    MANAGER_GROUP,
)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "ai.message.import.order.mixin"]

    _ai_message_import_link = "sale_order_id"

    ai_message_import_document_ids = fields.One2many(
        "ai.message.import.document",
        "sale_order_id",
        string="Received orders",
        copy=False,
        groups=MANAGER_GROUP,
    )
    ai_message_import_incident_ids = fields.One2many(
        "mail.message.import.incident",
        "sale_order_id",
        string="Document incidents",
        copy=False,
        groups=MANAGER_GROUP,
    )
    ai_message_import_change_ids = fields.One2many(
        "ai.message.import.change",
        "sale_order_id",
        string="Changes by the AI",
        copy=False,
        groups=MANAGER_GROUP,
    )

    def action_confirm(self):
        self._ai_message_forbid_automation()
        res = super().action_confirm()
        self._ai_message_learn_ai_products()
        return res

    def action_cancel(self):
        self._ai_message_forbid_automation()
        return super().action_cancel()

    def _action_cancel(self):
        self._ai_message_forbid_automation()
        return super()._action_cancel()

    def _ai_message_confirm(self):
        return self.action_confirm()


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["sale.order.line", "ai.message.import.order.line.mixin"]
