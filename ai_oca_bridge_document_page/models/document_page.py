from odoo import models


class DocumentPage(models.Model):
    _inherit = ["document.page", "ai.bridge.thread"]
    _name = "document.page"
