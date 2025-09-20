# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class McpPromptGetWizard(models.TransientModel):
    _name = "mcp.prompt.get.wizard"
    _description = "MCP Prompt Get Wizard"

    prompt_id = fields.Many2one(
        "mcp.prompt", string="Prompt", required=True, readonly=True
    )
    server_id = fields.Many2one(
        "mcp.server", string="Server", required=True, readonly=True
    )
    arguments = fields.Text(
        default="{}",
        help="JSON object with the arguments for the prompt",
    )
    result = fields.Text(readonly=True)

    @api.constrains("arguments")
    def _check_arguments(self):
        for record in self:
            try:
                args_json = json.loads(record.arguments)
                if not isinstance(args_json, dict):
                    raise ValidationError(_("Arguments must be a JSON object"))
            except json.JSONDecodeError:
                raise ValidationError(_("Arguments must be valid JSON")) from None

    def action_get_prompt(self):
        """Get the prompt with the provided arguments."""
        self.ensure_one()

        try:
            arguments = json.loads(self.arguments)
            result = self.prompt_id.get_prompt(arguments)

            # Format the result for display
            if isinstance(result, dict):
                self.result = json.dumps(result, indent=2)
            else:
                self.result = str(result)

            return {
                "type": "ir.actions.act_window",
                "res_model": "mcp.prompt.get.wizard",
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
                "context": self.env.context,
            }

        except Exception as e:
            raise UserError(
                _("Error getting prompt: %(error)s") % {"error": str(e)}
            ) from None
