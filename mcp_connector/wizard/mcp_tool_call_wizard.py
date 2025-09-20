# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class McpToolCallWizard(models.TransientModel):
    _name = "mcp.tool.call.wizard"
    _description = "MCP Tool Call Wizard"

    tool_id = fields.Many2one("mcp.tool", string="Tool", required=True, readonly=True)
    server_id = fields.Many2one(
        "mcp.server", string="Server", required=True, readonly=True
    )
    arguments = fields.Text(
        required=True,
        default="{}",
        help="JSON object with the arguments for the tool",
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

    def action_call_tool(self):
        """Call the tool with the provided arguments."""
        self.ensure_one()

        try:
            arguments = json.loads(self.arguments)
            result = self.tool_id.call_tool(arguments)

            # Format the result for display
            if isinstance(result, dict):
                self.result = json.dumps(result, indent=2)
            else:
                self.result = str(result)

            return {
                "type": "ir.actions.act_window",
                "res_model": "mcp.tool.call.wizard",
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
                "context": self.env.context,
            }

        except Exception as e:
            raise UserError(
                _("Error calling tool: %(error)s") % {"error": str(e)}
            ) from None
