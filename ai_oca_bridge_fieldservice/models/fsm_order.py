# Copyright 2025 Marcel Savegnago - Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class FSMOrder(models.Model):

    _name = "fsm.order"
    _inherit = ["fsm.order", "ai.bridge.thread"]
