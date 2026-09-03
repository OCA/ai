# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class AiAgent(models.Model):
    _name = "ai.agent"
    _description = "AI Agent"
    _order = "name asc"

    name = fields.Char(required=True)
    persona_id = fields.Many2one(
        "ai.persona",
        ondelete="restrict",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Dedicated User Account",
        required=True,
        domain="[('is_ai_agent', '=', True)]",
        context={"active_test": False},
        help="Dedicated user account under which tool calls execute "
        "when mode is dedicated_agent.",
    )
    execution_mode = fields.Selection(
        [
            ("user_context", "Connected User Context"),
            ("dedicated_agent", "Dedicated Agent User"),
        ],
        default="user_context",
        required=True,
        help="user_context: executes tool calls under calling user context.\n"
        "dedicated_agent: executes tool calls under the assigned user_id.",
    )
    active = fields.Boolean(default=True)
    description = fields.Text()
