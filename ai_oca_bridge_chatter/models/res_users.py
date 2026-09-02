# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    ai_bridge_id = fields.Many2one(
        "ai.bridge", string="AI Bridge", domain=[("usage", "=", "chatter")]
    )

    def _compute_im_status(self):
        """
        Override to set im_status to 'online' for users
        that have an associated user with an AI bridge.
        Useful for Live chat
        """
        for record in self.filtered(lambda r: r.ai_bridge_id):
            record.im_status = "online"
        to_process = self.filtered(lambda r: not r.ai_bridge_id)
        if not to_process:
            return
        return super(ResUsers, to_process)._compute_im_status()
