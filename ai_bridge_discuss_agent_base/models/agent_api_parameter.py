import re

from odoo import fields, models
from odoo.tools.safe_eval import safe_eval


class AgentAPIParameter(models.Model):
    _name = "agent.api.parameter"
    _description = "Agent API Parameter"

    name = fields.Char(required=True)
    value = fields.Char(required=True)
    parameter_type = fields.Selection(
        [
            ("sender", "Sender Partner"),
            ("receiver", "Receiver Partner"),
            ("general", "General Context"),
        ],
        required=True,
        default="general",
        help=(
            "Defines if the parameter is for the sender, receiver, "
            "or general context."
        ),
    )

    def evaluate_parameter(self, obj=None):
        self.ensure_one()
        if "{" in self.value and "}" in self.value:

            def _replace_expression(match):
                expr = match.group(1)
                try:
                    return str(safe_eval(expr, {"object": obj}, {}))
                except Exception as e:
                    return f"[Eval Error: {e}]"

            return re.sub(r"{(.*?)}", _replace_expression, self.value or "")

        return self.value
