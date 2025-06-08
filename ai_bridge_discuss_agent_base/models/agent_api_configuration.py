from odoo import fields, models


class AgentAPIParameter(models.Model):
    _name = "agent.api.configuration"
    _description = "Agent API Configuration"

    name = fields.Char(required=True)
    api_parameter_ids = fields.Many2many(
        comodel_name="agent.api.parameter",
        string="API Parameters",
    )
