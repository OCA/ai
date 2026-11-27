# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mail import html_sanitize


class TaskDescriptionWizard(models.TransientModel):
    _name = "ai.oca.bridge.openwebui.task.description.wizard"
    _description = "Review OpenWebUI Task Description"

    task_id = fields.Many2one("project.task", required=True, readonly=True)
    description = fields.Html(required=True, sanitize=True)

    def action_apply(self):
        self.ensure_one()
        task = self.task_id
        if not task.exists():
            raise UserError(_("The project task no longer exists."))
        if not self.env.user._is_internal():
            raise AccessError(_("Only internal users can update task descriptions."))
        task.check_access("write")
        task.write({"description": html_sanitize(self.description or "")})
        return {"type": "ir.actions.act_window_close"}
