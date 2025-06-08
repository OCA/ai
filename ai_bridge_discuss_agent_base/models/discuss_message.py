from odoo import fields, models


class Message(models.Model):
    _inherit = "mail.message"

    is_ai_agent_failed = fields.Boolean(
        string="Is AI Agent Failed",
        help=(
            "Indicates if the message is a response to a failure in"
            " getting a response from an AI agent."
        ),
    )
