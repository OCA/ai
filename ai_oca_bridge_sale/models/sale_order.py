from odoo import models


class SaleOrder(models.Model):
    _inherit = ["sale.order", "ai.bridge.thread"]
    _name = "sale.order"
