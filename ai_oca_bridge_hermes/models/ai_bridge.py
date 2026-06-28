# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    usage = fields.Selection(
        selection_add=[("hermes", "Hermes AI")],
        ondelete={"hermes": "set default"},
    )
    payload_type = fields.Selection(
        selection_add=[("hermes", "Hermes Chatter")],
        ondelete={"hermes": "set default"},
    )
    hermes_gateway_id = fields.Many2one(
        "hermes.gateway",
        string="Hermes Gateway",
        help="Link this bridge to a specific Hermes gateway configuration.",
    )

    def _prepare_payload_hermes(self, record=None, **kwargs):
        """Prepare payload for Hermes gateway with conversation history."""
        payload = self._prepare_payload_chatter(record=record, **kwargs)

        if record and record._name == "mail.message":
            channel = self.env["discuss.channel"].browse(record.res_id)
            history = self._get_channel_history(channel, limit=20)
            payload["history"] = history
            payload["session_key"] = self._get_session_key(channel, payload)

        return payload

    def _get_channel_history(self, channel, limit=20):
        """Fetch recent conversation history for context."""
        messages = self.env["mail.message"].search(
            [
                ("res_id", "=", channel.id),
                ("model", "=", "discuss.channel"),
                ("message_type", "=", "comment"),
            ],
            order="date asc",
            limit=limit,
        )

        return [
            {
                "role": "assistant" if msg.author_id.user_ids.ai_bridge_id else "user",
                "body": msg.body,
                "date": msg.date.isoformat() if msg.date else None,
                "author_name": msg.author_id.name,
            }
            for msg in messages
        ]

    def _get_session_key(self, channel, payload):
        """Generate a unique session key for Hermes."""
        odoo_info = payload.get("_odoo", {})
        db_hash = odoo_info.get("db_hash", "unknown")
        return f"odoo:{db_hash}:channel_{channel.id}"
