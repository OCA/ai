# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class McpResourceReadWizard(models.TransientModel):
    _name = "mcp.resource.read.wizard"
    _description = "MCP Resource Read Wizard"

    resource_id = fields.Many2one(
        "mcp.resource", string="Resource", required=True, readonly=True
    )
    server_id = fields.Many2one(
        "mcp.server", string="Server", required=True, readonly=True
    )
    is_template = fields.Boolean(readonly=True)
    uri = fields.Char(readonly=True)
    uri_template = fields.Char(string="URI Template", readonly=True)
    parameters = fields.Text(
        default="{}",
        help="JSON object with parameters for the URI template",
    )
    content = fields.Text(readonly=True)
    mime_type = fields.Char(string="MIME Type", readonly=True)

    @api.constrains("parameters")
    def _check_parameters(self):
        for record in self:
            if record.is_template and record.parameters:
                try:
                    params_json = json.loads(record.parameters)
                    if not isinstance(params_json, dict):
                        raise ValidationError(_("Parameters must be a JSON object"))
                except json.JSONDecodeError:
                    raise ValidationError(_("Parameters must be valid JSON")) from None

    def action_read_resource(self):
        """Read the resource with the provided parameters."""
        self.ensure_one()

        try:
            if self.is_template:
                params = json.loads(self.parameters) if self.parameters else {}
                result = self.resource_id.read_resource(params=params)
            else:
                result = self.resource_id.read_resource()

            # Extract the content from the result
            if isinstance(result, dict) and "contents" in result and result["contents"]:
                content = result["contents"][0]
                self.content = content.get("text", "")
                self.mime_type = content.get("mimeType", "text/plain")
            else:
                self.content = str(result)
                self.mime_type = "text/plain"

            return {
                "type": "ir.actions.act_window",
                "res_model": "mcp.resource.read.wizard",
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
                "context": self.env.context,
            }

        except Exception as e:
            raise UserError(
                _("Error reading resource: %(error)s") % {"error": str(e)}
            ) from None
