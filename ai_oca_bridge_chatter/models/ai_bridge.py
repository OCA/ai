# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    usage = fields.Selection(
        selection_add=[("chatter", "Chatter")], ondelete={"chatter": "set default"}
    )
    payload_type = fields.Selection(
        selection_add=[("chatter", "Chatter")], ondelete={"chatter": "set default"}
    )

    def _prepare_payload_chatter(self, record=None, **kwargs):
        if not record:
            record = self.env["mail.message"].search([], limit=1)
        if record._name != "mail.message":
            raise ValueError(_("The record must be a mail.message instance."))
        return {
            "message": {
                "res_id": record.res_id,
                "model": record.model,
                "body": record.body,
                "author_id": record.author_id.id,
                "subject": record.subject,
                "date": record.date.isoformat(),
                "author_name": record.author_id.name,
            }
        }
