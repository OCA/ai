# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from odoo.addons.ai_message_import.models.ai_message_import_order_mixin import (
    MANAGER_GROUP,
)


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "ai.message.import.order.mixin"]

    _ai_message_import_link = "purchase_order_id"

    ai_message_import_document_ids = fields.One2many(
        "ai.message.import.document",
        "purchase_order_id",
        string="Received documents",
        copy=False,
        groups=MANAGER_GROUP,
    )
    ai_message_import_incident_ids = fields.One2many(
        "mail.message.import.incident",
        "purchase_order_id",
        string="Document incidents",
        copy=False,
        groups=MANAGER_GROUP,
    )
    ai_message_import_change_ids = fields.One2many(
        "ai.message.import.change",
        "purchase_order_id",
        string="Changes by the AI",
        copy=False,
        groups=MANAGER_GROUP,
    )

    def button_confirm(self):
        self._ai_message_forbid_automation()
        res = super().button_confirm()
        self._ai_message_learn_ai_products()
        return res

    def button_approve(self, force=False):
        self._ai_message_forbid_automation()
        return super().button_approve(force=force)

    def button_cancel(self):
        self._ai_message_forbid_automation()
        return super().button_cancel()

    def _ai_message_confirm(self):
        return self.with_context(validate_analytic=True).button_confirm()


class PurchaseOrderLine(models.Model):
    _name = "purchase.order.line"
    _inherit = ["purchase.order.line", "ai.message.import.order.line.mixin"]
