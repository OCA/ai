# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo import models, tools


# pylint: disable=consider-merging-classes-inherited
class AiBridgeOpenWebuiAttachments(models.Model):
    _inherit = "ai.bridge"

    def _openwebui_message_attachments(self, message):
        """Find files attached to a Discuss message.

        Discuss stores composer uploads on the channel (res_model/res_id),
        rather than always linking them through message_attachment_rel.
        """
        attachments = message.attachment_ids.sudo()
        if message.model == "discuss.channel" and message.res_id:
            previous = (
                self.env["mail.message"]
                .sudo()
                .search(
                    [
                        ("model", "=", message.model),
                        ("res_id", "=", message.res_id),
                        ("message_type", "=", "comment"),
                        ("id", "<", message.id),
                    ],
                    order="id desc",
                    limit=1,
                )
            )
            domain = [
                ("res_model", "=", "discuss.channel"),
                ("res_id", "=", message.res_id),
                ("create_date", "<=", message.create_date),
            ]
            if previous:
                domain.append(("create_date", ">", previous.create_date))
            attachments |= self.env["ir.attachment"].sudo().search(domain)
        return attachments

    def _openwebui_message_content(self, message):
        text = tools.html2plaintext(message.body or "").strip()
        images = []
        for attachment in self._openwebui_message_attachments(message):
            if not attachment.mimetype or not attachment.mimetype.startswith("image/"):
                continue
            raw = attachment.raw
            if not raw:
                continue
            encoded = base64.b64encode(raw).decode("ascii")
            images.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{attachment.mimetype};base64,{encoded}",
                    },
                }
            )
        if not images:
            return text
        return [{"type": "text", "text": text}, *images]
