# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    usage = fields.Selection(
        selection_add=[("web_editor", "HTML Editor")],
        ondelete={"web_editor": "set default"},
    )

    @api.onchange("payload_type", "usage")
    def _onchange_openwebui_web_editor(self):
        for bridge in self:
            if bridge.payload_type == "openwebui" and bridge.usage == "web_editor":
                bridge.result_kind = "immediate"
                bridge.result_type = "none"
