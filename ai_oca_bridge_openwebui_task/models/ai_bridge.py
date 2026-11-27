# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    usage = fields.Selection(
        selection_add=[("project_task", "Project Task Description")],
        ondelete={"project_task": "set default"},
    )

    @api.onchange("payload_type", "usage")
    def _onchange_openwebui_project_task(self):
        for bridge in self:
            if bridge.payload_type == "openwebui" and bridge.usage == "project_task":
                bridge.result_kind = "immediate"
                bridge.result_type = "none"
