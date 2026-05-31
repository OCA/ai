# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib

from odoo import fields, models


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    hermes_gateway_id = fields.Many2one(
        "hermes.gateway",
        string="Hermes Gateway",
        help="If set, messages in this channel will be forwarded to Hermes.",
    )
    hermes_auto_respond = fields.Boolean(
        default=True,
        help="If checked, Hermes will automatically respond "
        "to messages in this channel.",
    )

    def _get_hermes_gateway(self):
        """Find the Hermes gateway for this channel.

        For channels with explicit gateway set, return it.
        For DM chats with Hermes AI user, find the first active gateway.
        """
        self.ensure_one()
        if self.hermes_gateway_id:
            return self.hermes_gateway_id

        # For DM chats, check if one of the members is an AI user
        if self.channel_type == "chat":
            for member in self.channel_member_ids:
                if member.partner_id.user_ids.ai_bridge_id:
                    # Find a gateway using this AI user
                    gateway = self.env["hermes.gateway"].search(
                        [
                            ("ai_user_id", "=", member.partner_id.user_ids.id),
                            ("active", "=", True),
                        ],
                        limit=1,
                    )
                    if gateway:
                        return gateway
        return False

    def message_post(self, **kwargs):
        """Override to queue messages for Hermes when a gateway is configured."""
        message = super().message_post(**kwargs)

        # Skip if message is from an AI user (prevent loops)
        if message.author_id.user_ids.ai_bridge_id:
            return message

        # Check if this channel has a Hermes gateway (direct or via DM)
        gateway = self._get_hermes_gateway()
        if not gateway:
            return message

        # Validate gateway is active and has an AI user
        if not gateway.active or not gateway.ai_user_id:
            return message

        # Check if gateway monitors specific channels (only for non-DM)
        if (
            gateway.channel_ids
            and self.channel_type != "chat"
            and self not in gateway.channel_ids
        ):
            return message

        # Check auto-respond is enabled
        if not self.hermes_auto_respond:
            return message

        # Queue the message for Hermes
        self.env["hermes.message.queue"].sudo().create(
            {
                "channel_id": self.id,
                "body": message.body,
                "author_id": message.author_id.id,
                "gateway_id": gateway.id,
                "db_hash": self._get_db_hash(),
            }
        )

        # Trigger typing indicator on the AI user
        for member in self.channel_member_ids:
            if member.partner_id == gateway.ai_user_id.partner_id:
                member._notify_typing(is_typing=True)

        return message

    def _get_db_hash(self):
        """Compute a hash identifying this database for Hermes session keys."""
        IrConfig = self.env["ir.config_parameter"].sudo()
        dbuuid = IrConfig.get_param("database.uuid")
        db_create_date = IrConfig.get_param("database.create_date")
        dbname = self.env.cr.dbname
        return hashlib.sha256(
            f"{dbuuid}:{db_create_date}:{dbname}".encode()
        ).hexdigest()[:16]
