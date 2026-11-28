# Copyright 2026 Coopdevs
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiToolConfirmFakeDocument(models.Model):
    """A document with a chatter, for the tests only."""

    _name = "ai.tool.confirm.fake.document"
    _description = "AI Tool Confirm Fake Document"
    _inherit = ["mail.thread"]

    name = fields.Char()
    user_id = fields.Many2one("res.users", tracking=True)
