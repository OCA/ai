# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _compute_im_status(self):
        """
        Override to set im_status to 'online' for partners
        that have an associated user with an AI bridge.
        It will be shown in general chatter as online.
        """
        for record in self.filtered(lambda r: r.user_ids.ai_bridge_id):
            record.im_status = "online"
        to_process = self.filtered(lambda r: not r.user_ids.ai_bridge_id)
        if not to_process:
            return
        return super(ResPartner, to_process)._compute_im_status()
