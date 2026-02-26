# Copyright 2025 Pierre Verkest
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)
import json
import logging

from odoo import api, fields, models
from odoo.tools import html2plaintext, json_default

_logger = logging.getLogger(__name__)


class AiThread(models.Model):
    _name = "ai.thread"
    _inherit = "ai.llm.client"
    _description = "AI Conversation Thread"
    _order = "create_date desc"

    name = fields.Char(string="Reference", required=True, default="New Thread")
    res_model = fields.Char(string="Related Document Model", required=True, index=True)
    res_id = fields.Integer(string="Related Document ID", required=True, index=True)
    user_id = fields.Many2one(
        "res.users",
        string="User",
        default=lambda self: self.env.user,
        required=True,
        index=True,
    )
    message_ids = fields.One2many("ai.message", "thread_id", string="Messages")

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

    def _get_record_context(self, record):
        """Extract user-accessible fields into a JSON serializable dict."""
        self.ensure_one()
        context_data = {}
        if not record.exists():
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

    def _add_message(self, content, role="user"):
        return self.env["ai.message"].create(
            {
                "thread_id": self.id,
                "role": role,
                "content": content,
            }
        )

    def _get_chatter_history_content(self, record):
        """Extract and format the chatter history to send to the LLM."""
        if "message_ids" not in record._fields or not record.message_ids:
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
        record = self.env[self.res_model].browse(self.res_id)
        system_content = (
            "You are a helpful Odoo Assistant. "
            f"The user: {self.env.user.name}, is currently looking at "
            f"a record of type {self.res_model}."
            f"The user speak {self.env.user.partner_id.lang} which should be"
            "the prefered language for the responses specify."
        )
        if record.exists():
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

    def _generate_and_set_title(self, first_message_content):
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Provide a very "
                    "concise title (3-5 words max) summarizing the "
                    "user's request. Do not include quotes or extra "
                    "text. Reply in the user language "
                    f"({self.env.user.partner_id.lang})."
                ),
            },
            {"role": "user", "content": first_message_content},
        ]
        title = self.chat(prompt)
        if title:
            today_str = fields.Date.context_today(self).strftime("%Y-%m-%d")
            # Strip spaces and quotes
            title = title.strip(" \"'\n")
            self.name = f"[{today_str}] {title}"

    def action_send_message(self, content):
        self.ensure_one()
        is_first_message = not bool(self.message_ids)

        # 1. Create User Message
        self._add_message(content)

        if is_first_message:
            self._generate_and_set_title(content)

        ollama_messages = self._get_system_prompt() + self._get_thread_messages()
        _logger.debug("Content send to Ollama...\n%s", ollama_messages)
        # 3. Call LLM
        ai_content = self.chat(ollama_messages)

        # 4. Save Assistant Message
        if ai_content:
            self._add_message(ai_content, role="assistant")
            return {
                "status": "success",
                "content": ai_content,
                "thread_name": self.name,
            }

        return {"status": "error", "content": "No response from LLM"}
