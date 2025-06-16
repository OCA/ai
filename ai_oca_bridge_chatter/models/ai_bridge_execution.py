# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    chatter_user_id = fields.Many2one("res.users", readonly=True)

    def _get_channel(self):
        if self.ai_bridge_id.usage == "chatter":
            # For chatter usage, we need to get the channel from the message
            message = self.env["mail.message"].browse(self.res_id)
            if message.model != "mail.channel":
                raise ValueError(_("The message does not belong to any channel."))
            return (
                self.env["mail.channel"]
                .browse(message.res_id)
                .with_user(self.chatter_user_id.id)
            )
        return super()._get_channel()

    def _process_response_message(self, response):
        if self.ai_bridge_id.usage == "chatter":
            recipient = (
                self.env["mail.channel.member"]
                .sudo()
                .search(
                    [
                        ("partner_id", "=", self.chatter_user_id.partner_id.id),
                        ("channel_id", "=", self._get_channel().id),
                    ],
                    limit=1,
                )
            )
            recipient._notify_typing(is_typing=False)
            response["author_id"] = self.chatter_user_id.partner_id.id
            response["message_type"] = "comment"
        return super()._process_response_message(response)
