# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class McpTool(models.Model):
    _name = "mcp.tool"
    _description = "MCP Tool"
    _order = "server_id, name"

    name = fields.Char(string="Tool Name", required=True, index=True)
    server_id = fields.Many2one(
        "mcp.server", string="Server", required=True, ondelete="cascade", index=True
    )
    server_state = fields.Selection(
        related="server_id.state", string="Server Status", readonly=True
    )
    description = fields.Text()
    input_schema = fields.Text(help="JSON Schema for the tool parameters")
    output_schema = fields.Text(help="JSON Schema for the tool output")
    is_auto_approved = fields.Boolean(
        string="Auto Approved", compute="_compute_is_auto_approved", store=True
    )

    _sql_constraints = [
        (
            "server_name_uniq",
            "unique(server_id, name)",
            "Tool name must be unique per server!",
        )
    ]

    @api.constrains("input_schema", "output_schema")
    def _check_schemas(self):
        for record in self:
            # Validate input schema
            if record.input_schema:
                try:
                    schema_json = json.loads(record.input_schema)
                    if not isinstance(schema_json, dict):
                        raise ValidationError(_("Input schema must be a JSON object"))
                except json.JSONDecodeError:
                    raise ValidationError(
                        _("Input schema must be valid JSON")
                    ) from None

            # Validate output schema
            if record.output_schema:
                try:
                    schema_json = json.loads(record.output_schema)
                    if not isinstance(schema_json, dict):
                        raise ValidationError(_("Output schema must be a JSON object"))
                except json.JSONDecodeError:
                    raise ValidationError(
                        _("Output schema must be valid JSON")
                    ) from None

    @api.depends("server_id", "name")
    def _compute_is_auto_approved(self):
        for record in self:
            auto_approve = record.server_id.auto_approve
            if auto_approve:
                try:
                    auto_approve_list = json.loads(auto_approve)
                    record.is_auto_approved = record.name in auto_approve_list
                except (json.JSONDecodeError, TypeError):
                    record.is_auto_approved = False
            else:
                record.is_auto_approved = False

    def action_call_tool(self):
        """Open a wizard to call the tool with parameters."""
        self.ensure_one()
        return {
            "name": _("Call Tool: %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "mcp.tool.call.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_tool_id": self.id,
                "default_server_id": self.server_id.id,
            },
        }

    def call_tool(self, arguments):
        """Call the tool with the provided arguments.

        Args:
            arguments (dict): The arguments to pass to the tool

        Returns:
            dict: The result of the tool call
        """
        self.ensure_one()

        if self.server_id.state != "running":
            raise UserError(_("Server is not running"))

        # Use the action_call_tool method in the McpServer model
        try:
            result = self.server_id.action_call_tool(self.name, arguments)
            return result
        except Exception as e:
            _logger.exception(
                "Error calling tool %(tool_name)s: %(error)s",
                {"tool_name": self.name, "error": str(e)},
            )
            raise UserError(
                _("Error calling tool: %(error)s") % {"error": str(e)}
            ) from None
