# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models

from ..services.sale_order_builder import SaleOrderBuilder


class AiMessageImportDocument(models.Model):
    _inherit = "ai.message.import.document"

    sale_order_id = fields.Many2one(
        "sale.order", string="Sales quotation", readonly=True, index=True
    )
    sale_state = fields.Selection(related="sale_order_id.state", string="Sales status")

    @api.model
    def _document_types(self):
        types = super()._document_types()
        types["sale"] = {
            "label": _("Customer order (sale)"),
            "builder": SaleOrderBuilder,
        }
        return types


class AiMessageImportDocumentLine(models.Model):
    _inherit = "ai.message.import.document.line"

    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Sales order line",
        readonly=True,
        ondelete="set null",
    )
