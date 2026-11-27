# Copyright 2025 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class AITaskThread(models.Model):
    _name = "ai.task.thread"
    _description = "AI Task Thread"
    _order = "create_date asc"

    message_id = fields.Many2one(
        "ai.message", required=True, ondelete="cascade", index=True
    )
    name = fields.Char(required=True)
    task_message_ids = fields.One2many(
        "ai.task.message", "task_thread_id", string="Task Messages"
    )
    payload = fields.Json()

    def _add_message(self, content, role="user", payload=None):
        vals = {
            "task_thread_id": self.id,
            "role": role,
            "content": content,
        }
        if payload is not None:
            vals["payload"] = payload
        return self.env["ai.task.message"].create(vals)
