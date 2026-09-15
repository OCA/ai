# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import fields, models


class HermesMessageQueue(models.Model):
    _name = "hermes.message.queue"
    _description = "Messages queued for Hermes"
    _order = "create_date asc, id asc"

    channel_id = fields.Many2one("discuss.channel", required=True, index=True)
    body = fields.Text(required=True)
    author_id = fields.Many2one("res.partner", string="Author")
    author_name = fields.Char(related="author_id.name", store=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        default="pending",
        index=True,
    )
    gateway_id = fields.Many2one("hermes.gateway", required=True, index=True)
    db_hash = fields.Char(help="Database hash for Hermes session key.")
    error_message = fields.Text()
    message_type = fields.Selection(
        [
            ("user", "User Message"),
            ("system", "System Event"),
            ("command", "Command"),
        ],
        default="user",
    )
    escalation_id = fields.Many2one(
        "mail.message",
        string="Escalation Message",
        help="Reference to the escalation message or ticket. Used by child modules.",
    )
    is_escalated = fields.Boolean(
        default=False,
        help="Checked when a human has taken over the conversation.",
    )

    def action_retry(self):
        """Reset failed messages to pending for reprocessing."""
        self.filtered(lambda m: m.state == "error").write(
            {"state": "pending", "error_message": False}
        )

    def _cleanup_old_messages(self):
        """Cron job: delete messages older than 7 days in done/error state."""
        cutoff = fields.Datetime.now() - timedelta(days=7)
        old_messages = self.search(
            [
                ("create_date", "<", cutoff),
                ("state", "in", ["done", "error"]),
            ]
        )
        if old_messages:
            old_messages.unlink()
