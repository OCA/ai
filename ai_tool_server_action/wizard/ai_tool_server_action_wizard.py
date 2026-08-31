# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AiToolServerActionWizard(models.TransientModel):
    _name = "ai.tool.server.action.wizard"
    _description = "Wizard to create AI Tool from Server Action"

    server_action_id = fields.Many2one("ir.actions.server", required=True)
    ai_tool_id = fields.Many2one("ai.tool")
    name = fields.Char(string="Tool Name", required=True)
    description = fields.Text(string="Tool Description", required=True)
    input_schema_json = fields.Text(string="Input Schema (JSON)", required=True)
    output_schema_json = fields.Text(string="Output Schema (JSON)", required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        server_action_id = self.env.context.get("default_server_action_id")
        if server_action_id:
            server_action = self.env["ir.actions.server"].browse(server_action_id)
            res["server_action_id"] = server_action.id
            if server_action.ai_tool_id:
                res["ai_tool_id"] = server_action.ai_tool_id.id
                res["name"] = server_action.ai_tool_id.name
                res["description"] = server_action.ai_tool_id.description
                res["input_schema_json"] = server_action.ai_tool_id.input_schema_json
                res["output_schema_json"] = server_action.ai_tool_id.output_schema_json
            else:
                res["name"] = server_action.name

                res["input_schema_json"] = (
                    "{\n"
                    '  "type": "object",\n'
                    '  "properties": {\n'
                    '    "active_id": {\n'
                    '      "type": "integer",\n'
                    '      "description": "Record ID (Required for MCP '
                    'or generic usage)"\n'
                    "    },\n"
                    '    "active_ids": {\n'
                    '      "type": "array",\n'
                    '      "items": {"type": "integer"},\n'
                    '      "description": "Record IDs (Required for MCP '
                    'or generic usage)"\n'
                    "    }\n"
                    "  }\n"
                    "}"
                )

                if server_action.state != "code":
                    res["output_schema_json"] = (
                        "{\n"
                        '  "type": "object",\n'
                        '  "properties": {\n'
                        '    "status": {"type": "string"},\n'
                        '    "message": {"type": "string"}\n'
                        "  }\n"
                        "}"
                    )
                else:
                    res["output_schema_json"] = "{}"
        return res

    def action_apply(self):
        self.ensure_one()
        vals = {
            "name": self.name,
            "description": self.description,
            "input_schema_json": self.input_schema_json,
            "output_schema_json": self.output_schema_json,
        }
        if self.ai_tool_id:
            self.ai_tool_id.sudo().write(vals)
        else:
            vals.update(
                {
                    "kind": "server_action",
                    "server_action_id": self.server_action_id.id,
                }
            )
            self.env["ai.tool"].sudo().create(vals)
        return {"type": "ir.actions.act_window_close"}
