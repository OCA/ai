from odoo import models


class MrpWorkorder(models.Model):
    _inherit = ["mrp.workorder", "ai.bridge.thread"]
    _name = "mrp.workorder"
