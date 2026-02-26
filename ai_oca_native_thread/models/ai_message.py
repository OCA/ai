# Copyright 2025 Pierre Verkest
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)
from odoo import fields, models


class AiMessage(models.Model):
    _name = "ai.message"
    _description = "AI Thread Message"
    _order = "create_date asc"

    thread_id = fields.Many2one(
        "ai.thread", required=True, ondelete="cascade", index=True
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
    content = fields.Text(required=True)
