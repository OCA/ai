# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiMessageImportChange(models.Model):
    """A change made by the module on an order."""

    _name = "ai.message.import.change"
    _description = "Order Change by the AI"
    _order = "create_date desc, id desc"

    create_date = fields.Datetime(string="Date", readonly=True)
    document_id = fields.Many2one(
        "ai.message.import.document", readonly=True, index=True
    )
    conversation_id = fields.Many2one(
        "mail.message.import.conversation", string="Conversation", readonly=True
    )
    sender_id = fields.Many2one(
        "mail.message.import.sender", string="Sender", readonly=True, index=True
    )
    company_id = fields.Many2one("res.company", readonly=True)
    processing_ref = fields.Char(string="Processing", readonly=True)
    operation = fields.Selection(
        [("create", "Creation"), ("update", "Update"), ("delete", "Removal")],
        readonly=True,
    )
    field_name = fields.Char(string="Technical field", readonly=True)
    field_label = fields.Char(string="Field", readonly=True)
    old_value = fields.Char(string="Previous value", readonly=True)
    new_value = fields.Char(string="New value", readonly=True)
    reason = fields.Text(string="Interpreted reason", readonly=True)
    message_ids = fields.Many2many(
        "mail.message.import.message",
        "ai_message_import_change_message_rel",
        "change_id",
        "message_id",
        string="Origin messages",
        readonly=True,
    )
