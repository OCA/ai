# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class MailMessageImportChannel(models.Model):
    """The documents of a receiving channel, on its card of the panel."""

    _inherit = "mail.message.import.channel"

    document_count = fields.Integer(compute="_compute_document_counters")
    review_count = fields.Integer(compute="_compute_document_counters")
    new_count = fields.Integer(compute="_compute_document_counters")

    def _compute_document_counters(self):
        Document = self.env["ai.message.import.document"]
        for channel in self:
            domain = [("channel_id", "=", channel.id)]
            documents = Document.search(domain + [("state", "!=", "cancelled")])
            channel.document_count = len(documents)
            channel.review_count = Document.search_count(domain + self._review_domain())
            channel.new_count = len(documents.filtered("is_new"))

    @api.model
    def _review_domain(self):
        """The documents that still need a person: pending, possible
        duplicates or with open incidents."""
        return [
            ("state", "!=", "cancelled"),
            "|",
            ("state", "in", ("pending", "duplicate")),
            ("incident_ids.state", "=", "open"),
        ]

    def action_view_documents(self):
        return self._action_related(
            "ai_message_import.action_ai_message_import_document",
            [("channel_id", "in", self.ids)],
        )

    def action_view_review(self):
        return self._action_related(
            "ai_message_import.action_ai_message_import_document_review",
            [("channel_id", "in", self.ids)],
            {"search_default_to_review": 1},
        )

    def action_view_new(self):
        return self._action_related(
            "ai_message_import.action_ai_message_import_document_new",
            [("channel_id", "in", self.ids)],
            {"search_default_new": 1},
        )
