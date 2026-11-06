# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    ai_connection_id = fields.Many2one(
        "ai.connection",
        string="AI Document Extraction Connection",
        help="AI connection used to extract invoice data on this journal. "
        "Falls back to the company AI connection when empty.",
    )
