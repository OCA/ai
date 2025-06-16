# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class MailChannel(models.Model):
    _inherit = "mail.channel"

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        if not message.body:
            return message
        if message.author_id.user_ids.ai_bridge_id:
            # Don't answer AI agents
            return message
        channel_recipient_ids = self.sudo().channel_member_ids.filtered(
            lambda recipient: recipient.partner_id != message.author_id
            and recipient.partner_id.user_ids
            and recipient.partner_id.user_ids.ai_bridge_id
            and self._eligibile_for_ai(message, recipient)
        )
        for recipient in channel_recipient_ids:
            recipient._notify_typing(is_typing=True)
            for user in recipient.partner_id.user_ids:
                for bridge in user.ai_bridge_id:
                    execution = self.env["ai.bridge.execution"].create(
                        {
                            "ai_bridge_id": bridge.id,
                            "model_id": self.sudo()
                            .env.ref("mail.model_mail_message")
                            .id,
                            "res_id": message.id,
                            "chatter_user_id": user.id,
                        }
                    )
                    execution._execute()
        return message

    def _eligibile_for_ai(self, message, recipient):
        if len(self.sudo().channel_member_ids) <= 2:
            return True
        if recipient.partner_id in message.partner_ids:
            # If the recipient is already in the message partners,
            # it was invoked by the user.
            # This will make it work on general channels
            return True
        # TODO: add more checks to determine if the message is eligible
        # for AI processing, like livechat messages.
        return False
