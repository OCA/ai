# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)

        # ai_oca_bridge_chatter already handles Discuss channels through its
        # mail_channel override. This adapter handles other mail.thread models,
        # such as project.task, without creating duplicate executions there.
        if self._name == "discuss.channel":
            return message

        if message.message_type != "comment":
            return message

        partners = message.partner_ids.sudo()
        ai_users = partners.mapped("user_ids").filtered(
            lambda user: user.ai_bridge_id
            and user.ai_bridge_id.usage == "chatter"
            and user.ai_bridge_id.payload_type == "openwebui"
            and user.ai_bridge_id.model_id
            and user.ai_bridge_id.model_id.model == self._name
        )

        for user in ai_users:
            bridge = user.ai_bridge_id
            if not bridge._enabled_for(self):
                continue
            execution = (
                self.env["ai.bridge.execution"]
                .sudo()
                .create(
                    {
                        "ai_bridge_id": bridge.id,
                        "model_id": self.env.ref("mail.model_mail_message").id,
                        "res_id": message.id,
                        "chatter_user_id": user.id,
                    }
                )
            )
            execution._execute()

        return message
