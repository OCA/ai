# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mail import html2plaintext, plaintext2html


# pylint: disable=consider-merging-classes-inherited
class ProjectTask(models.Model):
    _inherit = "project.task"

    def action_openwebui_draft_description(self):
        self.ensure_one()
        if not self.env.user._is_internal():
            raise AccessError(
                _("Only internal users can draft task descriptions with AI.")
            )
        self.check_access("read")

        bridges = (
            self.env["ai.bridge"]
            .sudo()
            .search(
                [
                    ("active", "=", True),
                    ("payload_type", "=", "openwebui"),
                    ("usage", "=", "project_task"),
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", self.env.company.id),
                ],
                order="sequence, id",
                limit=2,
            )
        )
        if not bridges:
            raise UserError(
                _(
                    "Configure one active OpenWebUI bridge with the "
                    "'Project Task Description' usage first."
                )
            )
        if len(bridges) != 1:
            raise UserError(
                _(
                    "There must be exactly one active OpenWebUI bridge for "
                    "project task descriptions."
                )
            )
        bridge = bridges.with_user(self.env.user)
        if bridge.model_id and bridge.model_id.model != "project.task":
            raise UserError(
                _(
                    "The Project Task Description bridge must not be "
                    "restricted to another Odoo model."
                )
            )
        if not bridge._enabled_for(self):
            raise AccessError(_("You are not allowed to use the configured AI bridge."))
        bridge.sudo()._openwebui_check_model()

        description = html2plaintext(self.description or "").strip()
        task_context_lines = [
            f"Task: {self.name}",
            f"Project: {self.project_id.display_name if self.project_id else ''}",
            f"Current description: {description or '(empty)'}",
        ]
        if self.date_deadline:
            task_context_lines.append(f"Deadline: {self.date_deadline}")
        if self.user_ids:
            task_context_lines.append(
                "Assignees: " + ", ".join(self.user_ids.mapped("name"))
            )
        if self.tag_ids:
            task_context_lines.append("Tags: " + ", ".join(self.tag_ids.mapped("name")))
        messages = [
            {
                "role": "system",
                "content": (
                    "You help write clear, concise, actionable Odoo project task "
                    "descriptions. Use the language of the task context. Do not invent "
                    "facts, dates, people, commitments or technical details. Preserve "
                    "correct existing facts. Return plain text only; do not return "
                    "HTML or Markdown fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Draft or improve the task description using only this context. "
                    "Return only the proposed description, with useful short "
                    "paragraphs or simple bullet points when appropriate.\n\n"
                    + "\n".join(task_context_lines)
                ),
            },
        ]
        generated = bridge.sudo()._openwebui_chat_completion(messages)
        wizard = self.env["ai.oca.bridge.openwebui.task.description.wizard"].create(
            {
                "task_id": self.id,
                "description": plaintext2html(generated),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("AI Task Description"),
            "res_model": "ai.oca.bridge.openwebui.task.description.wizard",
            "view_mode": "form",
            "res_id": wizard.id,
            "target": "new",
        }
