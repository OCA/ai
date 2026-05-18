# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from odoo import fields, models
from odoo.tools.mail import html_sanitize, plaintext2html

from ..tools import aitool

try:
    import markdown
except ImportError:
    markdown = None


class AiTool(models.Model):
    _name = "ai.tool"
    _description = "AI Tool"

    name = fields.Char(required=True)
    description = fields.Text()
    model_id = fields.Many2one(
        "ir.model", readonly=True, required=True, ondelete="cascade"
    )
    function_name = fields.Char(readonly=True, required=True)
    kind = fields.Selection(
        [
            ("generic", "Generic"),
            ("generic_model", "Generic but requires a record to work"),
            ("record", "Record"),
        ],
        readonly=True,
        required=True,
        default="record",
    )

    def _get_tool_definition(self):
        func = getattr(self.env[self.model_id.model], self.function_name)
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": func._ai_tool["input_schema"],
            "outputSchema": func._ai_tool["output_schema"],
        }

    @aitool(
        input_schema={},
        output_schema={
            "date": {"type": "date"},
        },
    )
    def _ai_get_date(self):
        return {"date": date.today().isoformat()}

    @aitool(
        input_schema={
            "message": {"type": "string"},
        },
        required_inputs=["message"],
        output_schema={},
    )
    def _ai_post_message(self, message=None, record=None, **kwargs):
        if not record or not record.exists():
            raise ValueError("Record must be provided and exist to post a message")
        record.message_post(body=self._ai_post_message_parse_body(message))
        return {}

    def _ai_post_message_parse_body(self, message):
        """
        Using markdown library if available to convert markdown to html,
        otherwise using plaintext2html as fallback
        """
        if markdown:
            return html_sanitize(markdown.markdown(message))
        return plaintext2html(message)

    def _execute_tool(self, *args, record=None, **kwargs):
        if self.kind == "generic":
            return getattr(self.env[self.model_id.model], self.function_name)(
                *args, **kwargs
            )
        if not record:
            raise ValueError("Record must be provided for non-generic tools")
        if self.kind == "generic_model":
            return getattr(self.env[self.model_id.model], self.function_name)(
                *args, record=record, **kwargs
            )
        elif record._name != self.model_id.model:
            raise ValueError(
                f"Record model {record._name} does not match tool "
                f"model {self.model_id.model}"
            )
        return getattr(record, self.function_name)(*args, **kwargs) or {}
