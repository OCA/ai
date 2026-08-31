# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    ai_tool_ids = fields.One2many(
        "ai.tool",
        "server_action_id",
        string="AI Tools",
    )
    ai_tool_id = fields.Many2one(
        "ai.tool",
        string="AI Tool",
        compute="_compute_ai_tool_id",
    )
    ai_tool_description = fields.Text(
        compute="_compute_ai_tool_fields",
        inverse="_inverse_ai_tool_description",
        string="AI Tool Description",
    )
    input_schema_json = fields.Text(
        compute="_compute_ai_tool_fields",
        inverse="_inverse_input_schema_json",
        string="AI Tool Input Schema",
    )
    output_schema_json = fields.Text(
        compute="_compute_ai_tool_fields",
        inverse="_inverse_output_schema_json",
        string="AI Tool Output Schema",
    )

    @api.depends("ai_tool_ids")
    def _compute_ai_tool_id(self):
        for rec in self:
            rec.ai_tool_id = rec.ai_tool_ids[:1]

    @api.depends(
        "ai_tool_ids.input_schema_json",
        "ai_tool_ids.output_schema_json",
        "ai_tool_ids.description",
    )
    def _compute_ai_tool_fields(self):
        for rec in self:
            rec.ai_tool_description = rec.ai_tool_id.description
            rec.input_schema_json = rec.ai_tool_id.input_schema_json
            rec.output_schema_json = rec.ai_tool_id.output_schema_json

    def _inverse_ai_tool_description(self):
        for rec in self:
            if rec.ai_tool_id:
                rec.ai_tool_id.sudo().description = rec.ai_tool_description

    def _inverse_input_schema_json(self):
        for rec in self:
            if rec.ai_tool_id:
                rec.ai_tool_id.sudo().input_schema_json = rec.input_schema_json

    def _inverse_output_schema_json(self):
        for rec in self:
            if rec.ai_tool_id:
                rec.ai_tool_id.sudo().output_schema_json = rec.output_schema_json

    def action_open_ai_tool_wizard(self):
        self.ensure_one()
        return {
            "name": "Create AI Tool",
            "type": "ir.actions.act_window",
            "res_model": "ai.tool.server.action.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_server_action_id": self.id},
        }
