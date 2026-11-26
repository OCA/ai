# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class MailMessageImportMessage(models.Model):
    """The documents the AI found in a received message."""

    _inherit = "mail.message.import.message"

    document_ids = fields.Many2many(
        "ai.message.import.document",
        "ai_message_import_document_message_rel",
        "message_id",
        "document_id",
        string="Documents",
        readonly=True,
    )
    document_count = fields.Integer(compute="_compute_document_count")

    @api.depends("document_ids")
    def _compute_document_count(self):
        for message in self:
            message.document_count = len(message.document_ids)

    def action_view_documents(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "ai_message_import.action_ai_message_import_document"
        )
        action["domain"] = [("id", "in", self.document_ids.ids)]
        action["context"] = {}
        return action
