# Copyright 2026 SDi <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AiConnectionExecutionIteration(models.Model):
    _name = "ai.connection.execution.iteration"
    _description = "AI Connection Execution Iteration"
    _order = "step_number asc, id asc"

    execution_id = fields.Many2one(
        "ai.connection.execution", string="Execution", required=True, ondelete="cascade"
    )
    step_number = fields.Integer(required=True)

    request_messages_json = fields.Json(string="Request Messages")
    response_message_json = fields.Json(string="Response Message")
    tool_calls_json = fields.Json(string="Tool Calls")
    tool_results_json = fields.Json(string="Tool Results")

    request_messages_txt = fields.Text(compute="_compute_txt_fields")
    response_message_txt = fields.Text(compute="_compute_txt_fields")
    tool_calls_txt = fields.Text(compute="_compute_txt_fields")
    tool_results_txt = fields.Text(compute="_compute_txt_fields")

    @api.depends(
        "request_messages_json",
        "response_message_json",
        "tool_calls_json",
        "tool_results_json",
    )
    def _compute_txt_fields(self):
        for rec in self:
            rec.request_messages_txt = (
                json.dumps(rec.request_messages_json, indent=2)
                if rec.request_messages_json
                else ""
            )
            rec.response_message_txt = (
                json.dumps(rec.response_message_json, indent=2)
                if rec.response_message_json
                else ""
            )
            rec.tool_calls_txt = (
                json.dumps(rec.tool_calls_json, indent=2) if rec.tool_calls_json else ""
            )
            rec.tool_results_txt = (
                json.dumps(rec.tool_results_json, indent=2)
                if rec.tool_results_json
                else ""
            )

    @api.model
    def _autovacuum(self):
        """Delete iteration records older than 15 days to prevent bloat."""
        date_limit = fields.Datetime.now() - relativedelta(days=15)
        old_records = self.search([("create_date", "<", date_limit)])
        if old_records:
            old_records.unlink()
