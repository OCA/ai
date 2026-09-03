# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import fields, http
from odoo.http import request


class HermesPoll(http.Controller):
    """Endpoint for Hermes gateway to poll pending messages."""

    @http.route("/hermes/poll", type="json", auth="public", csrf=False)
    def hermes_poll(self, **kwargs):
        """Return pending messages for Hermes to process.

        Hermes gateway polls this endpoint periodically to fetch
        messages queued by Odoo users.
        """
        # Validate auth token from Authorization header
        auth_header = request.httprequest.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if auth_header else ""

        gateway = (
            request.env["hermes.gateway"]
            .sudo()
            .search([("webhook_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not gateway:
            return {"messages": [], "error": "Invalid token"}

        # Rate limiting (1 second minimum between polls)
        if (
            gateway.last_poll
            and (fields.Datetime.now() - gateway.last_poll).total_seconds() < 1
        ):
            return {"messages": [], "error": "Rate limited"}

        # Update last poll timestamp
        gateway.sudo().write({"last_poll": fields.Datetime.now()})

        # Reset messages stuck in processing for > 5 minutes
        stuck_domain = [
            ("state", "=", "processing"),
            ("gateway_id", "=", gateway.id),
            ("write_date", "<", fields.Datetime.now() - timedelta(minutes=5)),
        ]
        stuck = request.env["hermes.message.queue"].sudo().search(stuck_domain)
        if stuck:
            stuck.sudo().write({"state": "pending"})

        # Fetch pending messages
        pending = (
            request.env["hermes.message.queue"]
            .sudo()
            .search(
                [
                    ("state", "=", "pending"),
                    ("gateway_id", "=", gateway.id),
                ],
                order="create_date asc, id asc",
                limit=50,
            )
        )

        messages = []
        for msg in pending:
            msg_data = {
                "id": msg.id,
                "channel_id": msg.channel_id.id,
                "channel_name": msg.channel_id.name,
                "body": msg.body,
                "author_id": msg.author_id.id,
                "author_name": msg.author_name,
                "db_hash": msg.db_hash,
                "create_date": msg.create_date.isoformat() if msg.create_date else None,
            }
            # Include history if requested
            if kwargs.get("include_history"):
                msg_data["history"] = self._get_channel_history(msg.channel_id)
            messages.append(msg_data)
            # Mark as processing so we don't send again on next poll
            msg.sudo().write({"state": "processing"})

        return {"messages": messages, "gateway_id": gateway.id}

    def _get_channel_history(self, channel, limit=10):
        """Get recent message history for context."""
        messages = (
            request.env["mail.message"]
            .sudo()
            .search(
                [
                    ("res_id", "=", channel.id),
                    ("model", "=", "discuss.channel"),
                    ("message_type", "=", "comment"),
                ],
                order="date desc",
                limit=limit,
            )
        )
        return [
            {
                "role": "assistant" if msg.author_id.user_ids.ai_bridge_id else "user",
                "body": msg.body,
                "date": msg.date.isoformat() if msg.date else None,
            }
            for msg in reversed(messages)
        ]
