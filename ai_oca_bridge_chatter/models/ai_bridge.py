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
        parent = record.parent_id
        return {
            "message": {
                "res_id": record.res_id,
                "model": record.model,
                "body": record.body,
                "author_id": record.author_id.id,
                "subject": record.subject,
                "date": record.date.isoformat(),
                "author_name": record.author_id.name,
                "attachment_ids": record.attachment_ids.ids,
                "parent_id": parent.id if parent else False,
                "parent": self._prepare_payload_chatter_parent(parent),
            }
        }

    def _prepare_payload_chatter_parent(self, parent):
        """Serialize the replied-to message, if any, for the external agent."""
        if not parent:
            return False
        return {
            "id": parent.id,
            "body": parent.body,
            "author_id": parent.author_id.id,
            "author_name": parent.author_id.name,
            "date": parent.date.isoformat() if parent.date else False,
        }
