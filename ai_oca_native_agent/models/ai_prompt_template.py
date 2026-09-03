# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import html
import json
import logging

from lxml import etree

from odoo import fields, models
from odoo.tools import json_default

_logger = logging.getLogger(__name__)


def _safe_json_default(obj):
    try:
        return json_default(obj)
    except TypeError:
        return str(obj)


class AiPromptTemplate(models.Model):
    _name = "ai.prompt.template"
    _description = "AI System Prompt Template"
    _order = "name asc"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    prompt_type = fields.Selection(
        [
            ("system", "System Prompt"),
            ("planner", "Planner Prompt"),
            ("intent", "Intent Extraction Prompt"),
            ("synthesizer", "Synthesizer Prompt"),
            ("thread_title", "Thread Title Prompt"),
            ("user_wrapper", "User Request Wrapper"),
        ],
        required=True,
        default="system",
    )
    include_record_data = fields.Boolean(
        default=True,
        help="Injects the JSON representation of the current record in record_context",
    )
    include_record_chatter = fields.Boolean(
        string="Include Chatter History",
        default=True,
        help="Injects the chatter history in record_chatter",
    )
    template_text = fields.Text(required=True)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        "unique(code)",
        "The code of the prompt template must be unique!",
    )

    def _get_prompt_render_values(self, content="", thread=None, record=None, **kwargs):
        """Construct evaluation values for QWeb prompt rendering."""
        self.ensure_one()
        record = record or (thread.record if thread else None)
        prompt_render_values = {
            "user": self.env.user,
            "env": self.env,
            "company": self.env.company,
            "lang": self.env.lang or self.env.user.partner_id.lang or "en_US",
            "record": record,
            "thread": thread,
            "res_model": record._name if record else "",
            "res_id": record.id if record else False,
            "record_context": "",
            "record_chatter": "",
            "chatter_messages": "",
            "content": content or "",
        }
        if kwargs:
            prompt_render_values.update(kwargs)

        if record and record.exists():
            if "ai.thread" in self.env:
                ai_thread_model = self.env["ai.thread"]
                if self.include_record_data and not prompt_render_values.get(
                    "record_context"
                ):
                    context_data = ai_thread_model._get_record_context(record)
                    prompt_render_values["record_context"] = (
                        json.dumps(
                            context_data,
                            default=_safe_json_default,
                            ensure_ascii=False,
                        )
                        if context_data
                        else ""
                    )
                if self.include_record_chatter and not (
                    prompt_render_values.get("record_chatter")
                    or prompt_render_values.get("chatter_messages")
                ):
                    chatter_text = ai_thread_model._get_chatter_history_content(record)
                    prompt_render_values["record_chatter"] = chatter_text
                    prompt_render_values["chatter_messages"] = chatter_text

            if prompt_render_values.get("record_chatter") or prompt_render_values.get(
                "chatter_messages"
            ):
                sync_chatter = prompt_render_values.get(
                    "record_chatter"
                ) or prompt_render_values.get("chatter_messages")
                prompt_render_values["record_chatter"] = sync_chatter
                prompt_render_values["chatter_messages"] = sync_chatter

        return prompt_render_values

    def render(self, content="", thread=None, record=None, **kwargs):
        self.ensure_one()
        prompt_render_values = self._get_prompt_render_values(
            content=content, thread=thread, record=record, **kwargs
        )
        template_content = (self.template_text or "").strip()
        if not template_content:
            return ""

        try:
            xml_text = f"<t>{template_content}</t>"
            tree = etree.fromstring(xml_text)
            rendered = self.env["ir.qweb"]._render(tree, values=prompt_render_values)
            return html.unescape(str(rendered))
        except Exception as err:
            _logger.warning(
                "Failed to render QWeb prompt template '%s' (%s), falling back: %s",
                self.code,
                type(err).__name__,
                err,
            )
            try:
                str_context = {str(k): v for k, v in prompt_render_values.items()}
                return template_content.format(**str_context)
            except Exception:
                return template_content
