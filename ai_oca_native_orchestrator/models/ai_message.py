# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AiMessage(models.Model):
    _inherit = "ai.message"

    def _process_assistant_message(self):
        self.ensure_one()
        if not self.exists() or self.status == "cancel":
            return

        task_thread = self._create_orchestrator_task_thread()
        ai_content = self._orchestrate_assistant_response(task_thread)
        if not ai_content:
            self.write(
                {"status": "cancel", "content": "Failed to get a response from LLM."}
            )
            self._notify_thread_bus_update(status="error")
            return

        self.write({"content": ai_content, "status": "done"})
        task_thread._add_message(ai_content, role="assistant")
        self._notify_thread_bus_update(status="success")

    def _create_orchestrator_task_thread(self):
        self.ensure_one()
        task_thread = (
            self.env["ai.task.thread"]
            .sudo()
            .create(
                {
                    "message_id": self.id,
                    "name": "Orchestrator Execution",
                }
            )
        )
        task_thread._add_message(
            self.content or "Processing user request",
            role="user",
        )
        return task_thread

    def _get_orchestrator_persona(self):
        self.ensure_one()
        if (
            self.thread_id
            and self.thread_id.agent_id
            and self.thread_id.agent_id.persona_id
        ):
            return self.thread_id.agent_id.persona_id
        return (
            self.env["ai.persona"].sudo().search([("is_default", "=", True)], limit=1)
        )

    def _get_orchestrator_system_prompt(self, persona=None):
        self.ensure_one()
        persona = persona or self._get_orchestrator_persona()
        if persona and persona.system_prompt_id:
            rendered = persona.system_prompt_id.render(thread=self.thread_id)
            if rendered:
                return [{"role": "system", "content": rendered}]
        return self.thread_id._get_system_prompt()

    def _get_orchestrator_llm_messages(self, persona=None):
        self.ensure_one()
        persona = persona or self._get_orchestrator_persona()
        system_messages = self._get_orchestrator_system_prompt(persona)

        thread_messages = self.thread_id.message_ids.filtered(
            lambda m: m.id != self.id and m.status != "cancel"
        ).sorted("create_date")

        if not thread_messages:
            return system_messages

        past_messages = thread_messages[:-1]
        latest_msg = thread_messages[-1]

        history_payload = []
        for msg in past_messages:
            history_payload.append(
                {
                    "role": msg.role,
                    "content": msg.content or "",
                }
            )

        user_content = latest_msg.content or ""
        if latest_msg.role == "user" and persona and persona.user_wrapper_prompt_id:
            rendered_user = persona.user_wrapper_prompt_id.render(
                content=user_content,
                thread=self.thread_id,
            )
            if rendered_user:
                user_content = rendered_user

        history_payload.append(
            {
                "role": latest_msg.role,
                "content": user_content,
            }
        )
        return system_messages + history_payload

    def _orchestrate_assistant_response(self, task_thread):
        self.ensure_one()
        llm_messages = self._get_orchestrator_llm_messages()
        return self.chat(
            llm_messages,
            model_type="fast",
        )

    def _notify_thread_bus_update(self, status="success"):
        self.ensure_one()
        user_partner = self.thread_id.user_id.partner_id
        payload = {
            "thread_id": self.thread_id.id,
            "thread_name": self.thread_id.name,
            "res_model": self.thread_id.res_model,
            "res_id": self.thread_id.res_id,
            "status": status,
            "message": self.thread_id.get_full_messages(self.thread_id.id)[-1],
        }
        self.env["bus.bus"]._sendone(user_partner, "ai_thread_update", payload)
