# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class HelpdeskTicket(models.Model):

    _name = "helpdesk.ticket"
    _inherit = ["helpdesk.ticket", "ai.bridge.thread"]
