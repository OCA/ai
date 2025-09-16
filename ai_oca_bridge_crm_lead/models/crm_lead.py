from odoo import models


class Lead(models.Model):
    _inherit = ["crm.lead", "ai.bridge.thread"]
    _name = "crm.lead"
