# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AiThread(models.Model):
    _inherit = "ai.thread"

    agent_id = fields.Many2one(
        "ai.agent",
        string="Orchestrator Agent",
        default=lambda self: self.env.ref(
            "ai_oca_native_orchestrator.default_main_orchestrator_agent",
            raise_if_not_found=False,
        ),
    )

    def _action_generate_thread_title(self):
        self.ensure_one()
        if self.name and self.name != self.env._("New Thread"):
            return
        user_messages = self.message_ids.filtered(lambda m: m.role == "user")
        if not user_messages:
            return
        first_message = user_messages.sorted("create_date")[0].content or ""
        if not first_message:
            return
        prompt_template = (
            self.env["ai.prompt.template"]
            .sudo()
            .search([("prompt_type", "=", "thread_title")], limit=1)
        )
        prompt = (
            prompt_template.render(content=first_message, thread=self)
            if prompt_template
            else (
                "Generate a concise, smart title (3 to 5 words max) in the user "
                f"language for a chat thread starting with:\n'{first_message}'\n"
                "Output ONLY the title, no quotes or punctuation."
            )
        )
        try:
            title = self.env["ai.llm.client"].chat(
                [{"role": "user", "content": prompt}],
                model_type="fast",
            )
            cleaned_title = (title or "").strip().strip('"').strip("'")
            if cleaned_title:
                self.name = cleaned_title
                return
        except Exception as e:
            _logger.warning("Failed to generate AI thread title via LLM: %s", e)

        super()._action_generate_thread_title()
