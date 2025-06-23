from odoo import fields, models


class BridgeTest(models.Model):
    _name = "bridge.test"
    _inherit = "ai.bridge.thread"
    _description = "Test Model for AI Bridge"

    name = fields.Char()
