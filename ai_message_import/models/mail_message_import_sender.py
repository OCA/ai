# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class MailMessageImportSender(models.Model):
    """The documents received from a sender."""

    _inherit = "mail.message.import.sender"

    document_count = fields.Integer(compute="_compute_document_count")

    def _compute_document_count(self):
        Document = self.env["ai.message.import.document"]
        for sender in self:
            sender.document_count = Document.search_count(
                [("sender_id", "=", sender.id), ("state", "!=", "cancelled")]
            )

    @api.model
    def _single_of_company(self):
        """The sender of the current company, when it has a single one."""
        senders = self.search([("company_id", "=", self.env.company.id)], limit=2)
        return senders if len(senders) == 1 else self.browse()

    def _lock_for_quotes(self):
        """Apply the documents of the sender one at a time.

        The row of the sender is updated: a concurrent application waits for
        this one, and fails with a serialization error (retried by Odoo) when
        this one committed meanwhile, instead of missing its order.
        """
        self.flush_recordset()
        self.env.cr.execute(
            """
            UPDATE mail_message_import_sender
               SET write_date = write_date
             WHERE id IN %s
            """,
            (tuple(self.ids),),
        )

    def action_view_documents(self):
        return self._action_related(
            "ai_message_import.action_ai_message_import_document",
            [("sender_id", "in", self.ids)],
        )
