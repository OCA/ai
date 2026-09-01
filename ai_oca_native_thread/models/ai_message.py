# Copyright 2025 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AiMessage(models.Model):
    _name = "ai.message"
    _inherit = "ai.llm.client"
    _description = "AI Thread Message"
    _order = "create_date asc"

    thread_id = fields.Many2one(
        "ai.thread", required=True, ondelete="cascade", index=True
    )
    role = fields.Selection(
        [
            ("system", "System"),
            ("user", "User"),
            ("assistant", "Assistant"),
            ("tool", "Tool"),
        ],
        required=True,
        default="user",
    )
    content = fields.Text()
    status = fields.Selection(
        [
            ("processing", "Processing"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="processing",
        required=True,
    )
    task_thread_ids = fields.One2many(
        "ai.task.thread", "message_id", string="task Threads"
    )

    queue_job_channel_name = fields.Char(compute="_compute_queue_job_channel_name")

    def _compute_queue_job_channel_name(self):
        for record in self:
            record.queue_job_channel_name = (
                f"{record.queue_job_channel_name}_{record.id}"
            )

    def _action_extract_intent(self):
        """Entry point called asynchronously by queue_job when a user sends a message.
        Delegates to _process_assistant_message() hook.
        """
        self.ensure_one()
        if not self.exists() or self.status == "cancel":
            return

        return self._process_assistant_message()

    def _process_assistant_message(self):
        """Extension hook for assistant message processing.
        Base implementation provides a direct completion using ai.llm.client.
        Overridden by ai_oca_native_orchestrator for multi-agent planning.
        """
        self.ensure_one()
        llm_messages = (
            self.thread_id._get_system_prompt() + self.thread_id._get_thread_messages()
        )
        ai_content = self.chat(llm_messages, model_type="fast")

        if not ai_content:
            self.write(
                {"status": "cancel", "content": "Failed to get a response from LLM."}
            )
            return

        self.write({"content": ai_content, "status": "done"})

        user_partner = self.thread_id.user_id.partner_id
        payload = {
            "thread_id": self.thread_id.id,
            "thread_name": self.thread_id.name,
            "res_model": self.thread_id.res_model,
            "res_id": self.thread_id.res_id,
            "status": "success",
            "message": self.thread_id.get_full_messages(self.thread_id.id)[-1],
        }
        self.env["bus.bus"]._sendone(user_partner, "ai_thread_update", payload)
