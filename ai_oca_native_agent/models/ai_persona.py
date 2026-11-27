# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class AiPersona(models.Model):
    _name = "ai.persona"
    _description = "AI Agent Persona"
    _order = "is_default desc, name asc"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    system_prompt_id = fields.Many2one(
        "ai.prompt.template",
        domain=[("prompt_type", "=", "system")],
    )
    user_wrapper_prompt_id = fields.Many2one(
        "ai.prompt.template",
        string="User Request Wrapper",
        domain=[("prompt_type", "=", "user_wrapper")],
    )
    description = fields.Text()
    is_default = fields.Boolean(default=False)

    _code_uniq = models.Constraint(
        "unique(code)",
        "The code of the persona must be unique!",
    )
