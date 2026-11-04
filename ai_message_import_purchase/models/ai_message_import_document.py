# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models

from ..services.purchase_order_builder import PurchaseOrderBuilder


class AiMessageImportDocument(models.Model):
    _inherit = "ai.message.import.document"

    purchase_order_id = fields.Many2one(
        "purchase.order", string="Purchase order", readonly=True, index=True
    )
    purchase_state = fields.Selection(
        related="purchase_order_id.state", string="Purchase status"
    )

    @api.model
    def _document_types(self):
        types = super()._document_types()
        types["purchase"] = {
            "label": _("Vendor quote (purchase)"),
            "builder": PurchaseOrderBuilder,
        }
        return types


class AiMessageImportDocumentLine(models.Model):
    _inherit = "ai.message.import.document.line"

    purchase_line_id = fields.Many2one(
        "purchase.order.line", string="Order line", readonly=True, ondelete="set null"
    )
