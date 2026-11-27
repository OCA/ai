# Copyright 2025 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class AITaskMessage(models.Model):
    _name = "ai.task.message"
    _description = "AI Task Message"
    _order = "create_date asc"

    task_thread_id = fields.Many2one(
        "ai.task.thread", required=True, ondelete="cascade", index=True
    )
    role = fields.Selection(
        [
            ("system", "System"),
            ("user", "User"),
            ("assistant", "Assistant"),
            ("tool", "Tool"),
        ],
        required=True,
        default="user",
    )
    content = fields.Text()
    payload = fields.Json()
