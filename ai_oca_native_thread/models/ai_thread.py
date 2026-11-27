# Copyright 2025 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
import logging
from textwrap import shorten

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import html2plaintext, json_default

_logger = logging.getLogger(__name__)

# todo move that to xml configuration
AI_THREAD_CHANNEL = "root.ai.thread"


class AiThread(models.Model):
    _name = "ai.thread"
    _description = "AI Conversation Thread"
    _order = "create_date desc"

    name = fields.Char(
        string="Reference", required=True, default=lambda self: self.env._("New Thread")
    )
    res_model = fields.Char(string="Related Document Model", required=True, index=True)
    res_id = fields.Many2oneReference(
        string="Related Document",
        model_field="res_model",
        required=True,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        index=True,
    )
    message_ids = fields.One2many("ai.message", "thread_id", string="Messages")
    queue_job_channel_name = fields.Char(compute="_compute_queue_job_channel_name")
    pending_job_count = fields.Integer(compute="_compute_pending_job_count")

    @property
    def record(self):
        """Return the related active Odoo recordset or None."""
        self.ensure_one()
        if self.res_model and self.res_id and self.res_model in self.env:
            rec = self.env[self.res_model].browse(self.res_id)
            return rec if rec.exists() else None
        return None

    @api.model
    def _get_field_type_to_ignore(self):
        return ("binary", "image")

    @api.model
    def _get_field_names_to_ignore(self):
        """Fields to ignore when extracting record context.
        We especially ignore mail.thread fields to put them in a separate block.
        """
        return (
            "message_ids",
            "message_follower_ids",
            "activity_ids",
            "message_partner_ids",
        )

    @api.model
    def _get_record_context(self, record):
        """Extract user-accessible fields into a JSON serializable dict."""
        context_data = {}
        if not record or not record.exists():
            return context_data

        try:
            # check access rights on the record
            record.check_access("read")
            # Using read()[0] returns primitive data ready for json
            # except for Many2one, One2many, Many2many, dates etc.
            raw_data = record.read()[0]
        except Exception:
            # If the user doesn't have read access to the record, we ignore.
            return context_data

        for field_name, value in raw_data.items():
            if not value:
                continue

            field = record._fields[field_name]
            # Skip massive fields or non-contextual fields
            if field.type in self._get_field_type_to_ignore():
                continue
            if field_name in self._get_field_names_to_ignore():
                continue

            if field.type == "many2one":
                # read() returns a tuple (id, display_name) for many2one
                context_data[field_name] = (
                    value[1] if isinstance(value, tuple) else value
                )
            elif field.type in ("one2many", "many2many"):
                # read() returns a list of IDs for x2many
                if isinstance(value, list):
                    related_records = self.env[field.comodel_name].browse(value)
                    context_data[field_name] = related_records.mapped("display_name")
            else:
                context_data[field_name] = value

        return context_data

    def _add_message(self, content, role="user", status="processing"):
        return self.env["ai.message"].create(
            {
                "thread_id": self.id,
                "role": role,
                "content": content,
                "status": status,
            }
        )

    @api.model
    def _get_chatter_history_content(self, record):
        """Extract and format the chatter history to send to the LLM."""
        if not record or not record.exists() or "message_ids" not in record._fields:
            return ""

        messages = record.message_ids.filtered(lambda m: m.body or m.subject)
        if not messages:
            return ""

        history = []
        # Sort oldest to newest for chronological reading by LLM
        for msg in messages.sorted("id"):
            author = msg.author_id.name or msg.email_from or "System"
            date = msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else ""
            body = html2plaintext(msg.body) if msg.body else ""
            subject = msg.subject or ""

            msg_block = f"[{date}] {author}:"
            if subject:
                msg_block += f"\nSubject: {subject}"
            if body:
                msg_block += f"\n{body.strip()}"

            history.append(msg_block)

        return "\n---\n".join(history)

    def _get_system_prompt(self) -> list[dict[str, str]]:
        # Inject basic system prompt with record context
        record = self.record
        system_content = (
            "You are a helpful Odoo Assistant. "
            f"The user: {self.env.user.name}, is currently looking at "
            f"a record of type {self.res_model}."
            f"The user speak {self.env.user.partner_id.lang} which should be"
            "the prefered language for the responses specify."
        )
        if record:
            system_content += (
                f"\nThe contextual record name is '{record.display_name}'."
            )
            context_data = self._get_record_context(record)
            if context_data:
                context_str = json.dumps(context_data, default=json_default, indent=2)
                system_content += (
                    "\nHere is the data associated with this record in "
                    f"JSON format:\n{context_str}\n"
                )

            if "message_ids" in record._fields:
                chatter_content = self._get_chatter_history_content(record)
                if chatter_content:
                    system_content += (
                        "\nHere is the chatter history of the record:\n"
                        f"{chatter_content}\n"
                    )
        return [{"role": "system", "content": system_content}]

    def _get_thread_messages(self) -> list[dict[str, str]]:
        return self.message_ids.sorted("create_date").mapped(
            lambda m: {"role": m.role, "content": m.content}
        )

    def _compute_queue_job_channel_name(self):
        for record in self:
            record.queue_job_channel_name = f"{AI_THREAD_CHANNEL}.id_{record.id}"

    def _action_generate_thread_title(self):
        self.ensure_one()
        if self.name and self.name != self.env._("New Thread"):
            return
        user_msgs = self.message_ids.filtered(lambda m: m.role == "user")
        if not user_msgs:
            return
        first_msg = user_msgs.sorted("create_date")[0].content or ""
        if first_msg:
            self.name = shorten(first_msg, width=30, placeholder="...")

    def action_send_message(self, content):
        self.ensure_one()

        # 1. Create User Message
        self._add_message(content, role="user", status="done")

        # 2. Update thread title synchronously if needed
        if not self.name or self.name == self.env._("New Thread"):
            self._action_generate_thread_title()

        # 3. Create placeholder Assistant Message
        assistant_msg = self._add_message("", role="assistant", status="processing")

        # 4. Call LLM asynchronously using queue_job
        assistant_msg.with_delay(
            channel=assistant_msg.queue_job_channel_name,
        )._action_extract_intent()

        return {
            "status": "pending",
            "thread_name": self.name,
            "assistant_message": {
                "id": assistant_msg.id,
                "role": assistant_msg.role,
                "content": assistant_msg.content,
                "status": assistant_msg.status,
                "task_threads": [],
            },
        }

    @api.model
    def get_full_messages(self, thread_id):
        thread = self.browse(thread_id)
        if not thread.exists():
            return []
        return thread._get_full_messages()

    def _get_full_messages(self):
        res = []
        for msg in self.message_ids.sorted("create_date"):
            msg_data = {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "status": msg.status,
                "task_threads": [],
            }
            for log_th in msg.task_thread_ids.sorted("create_date"):
                th_data = {"id": log_th.id, "name": log_th.name, "messages": []}
                for log_msg in log_th.task_message_ids.sorted("create_date"):
                    th_data["messages"].append(
                        {
                            "id": log_msg.id,
                            "role": log_msg.role,
                            "content": log_msg.content,
                        }
                    )
                msg_data["task_threads"].append(th_data)
            res.append(msg_data)
        return res

    @api.model
    def get_pending_job_count(self, thread_id):
        return self.browse(thread_id).pending_job_count

    def action_cancel_jobs(self):
        self.ensure_one()
        thread_jobs = self._get_related_jobs(
            Domain("state", "in", ["pending", "enqueued", "started"])
        )
        if thread_jobs:
            thread_jobs.button_cancelled()

        processing_messages = self.message_ids.filtered(
            lambda m: m.status == "processing"
        )
        if processing_messages:
            processing_messages.write(
                {"status": "cancel", "content": "Cancelled by user."}
            )

        user_partner = self.user_id.partner_id
        payload = {
            "thread_id": self.id,
            "thread_name": self.name,
            "res_model": self.res_model,
            "res_id": self.res_id,
            "status": "cancelled",
        }
        self.env["bus.bus"]._sendone(user_partner, "ai_thread_update", payload)
        return True

    def _compute_pending_job_count(self):
        for record in self:
            record.pending_job_count = len(
                record._get_related_jobs(
                    Domain("state", "in", ["pending", "enqueued", "started"])
                )
            )

    def _get_thread_queue_job_domain(self):
        self.ensure_one()
        return Domain(
            [
                ("model_name", "=", "ai.message"),
                ("method_name", "=", "_action_extract_intent"),
                ("channel", "like", f"{self.queue_job_channel_name}%"),
            ]
        )

    def _get_related_jobs(self, domain: Domain):
        """Return job recordset for the current thread
        AND the provided domain
        """
        self.ensure_one()
        return (
            self.env["queue.job"]
            .sudo()
            .search(self._get_thread_queue_job_domain() & domain)
        )
