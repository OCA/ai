from odoo import models


class SaleOrderLine(models.Model):
    _inherit = ["sale.order.line", "ai.bridge.thread"]
    _name = "sale.order.line"
