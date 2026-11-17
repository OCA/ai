# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.exceptions import UserError


class AiConnectionRun(models.Model):
    _name = "ai.connection.run"
    _description = "AI Connection Run"
    _order = "id desc"

    connection_id = fields.Many2one(
        "ai.connection", required=True, ondelete="cascade", readonly=True
    )
    state = fields.Selection(
        [
            ("running", "Running"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        default="running",
        required=True,
        readonly=True,
    )

    messages = fields.Json(default=list, readonly=True)
    tool_ids = fields.Many2many("ai.tool", readonly=True)
    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)
    max_iterations = fields.Integer(readonly=True)
    iteration = fields.Integer(default=0, readonly=True)
    prompt_tokens = fields.Integer(default=0, readonly=True)
    completion_tokens = fields.Integer(default=0, readonly=True)
    result = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    notify_res_model = fields.Char(readonly=True)
    notify_res_id = fields.Integer(readonly=True)
    notify_method = fields.Char(readonly=True)

    def _get_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return None
        return self.env[self.res_model].browse(self.res_id)

    def _get_notify_target(self):
        self.ensure_one()
        if not (self.notify_res_model and self.notify_method):
            return None
        if not self.notify_res_id:
            return self.env[self.notify_res_model]
        target = self.env[self.notify_res_model].browse(self.notify_res_id)
        return target if target.exists() else None

    def is_done(self):
        self.ensure_one()
        return self.state != "running"

    def get_result(self):
        self.ensure_one()
        if self.state == "running":
            raise UserError(self.env._("This AI connection run is not finished yet."))
        if self.state == "error":
            raise UserError(self.error_message)
        return (self.result, self.prompt_tokens, self.completion_tokens, self.iteration)

    def _notify_progress(self):
        self.ensure_one()
        target = self._get_notify_target()
        if target is not None:
            getattr(target, self.notify_method)(self)
