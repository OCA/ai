# Copyright 2026 Dixmit
# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.tools.mail import html2plaintext, html_sanitize, plaintext2html

try:
    import markdown
except ImportError:
    markdown = None


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[("ai_oca", "Run AI Prompt")],
        ondelete={"ai_oca": "cascade"},
    )
    ai_connection_id = fields.Many2one(
        "ai.connection",
        string="AI Connection",
        groups="base.group_system",
    )
    ai_tool_ids = fields.Many2many(
        "ai.tool",
        string="AI Tools",
        groups="base.group_system",
    )
    ai_prompt = fields.Html(
        string="AI Prompt",
        sanitize=False,
    )
    mailing_model_real = fields.Char(
        compute="_compute_mailing_model_real",
    )
    ai_output_mode = fields.Selection(
        [
            ("post_message", "Post Message"),
            ("update_record", "Update Record"),
            ("store_variable", "Store in Context Variable"),
            ("none", "None"),
        ],
        string="Output Mode",
        default="none",
        groups="base.group_system",
    )
    ai_update_record_field_id = fields.Many2one(
        "ir.model.fields",
        string="Update Record Field",
        domain=(
            "[('model_id', '=', model_id), "
            "('ttype', 'in', ['char', 'text', 'html'])]"
        ),
        groups="base.group_system",
    )
    ai_context_variable = fields.Char(
        string="Context Variable",
        groups="base.group_system",
        help=(
            "Name of the variable where the response will be stored "
            "in the evaluation context."
        ),
    )

    @api.depends("model_id")
    def _compute_mailing_model_real(self):
        for record in self:
            record.mailing_model_real = (
                record.model_id.model if record.model_id else False
            )

    def _run_action_ai_oca(self, eval_context=None):
        self.ensure_one()
        eval_context = eval_context or {}
        record = eval_context.get("record")
        prompt = self._get_ai_prompt(record)
        result = self.ai_connection_id._run(
            prompt,
            tools=self.ai_tool_ids,
            record=record,
        )[0]
        self._post_run_action_ai_run(result, eval_context, record)

    def _get_ai_prompt(self, record):
        self.ensure_one()
        prompt = self.ai_prompt or ""
        if record:
            prompt = str(
                self.env["mail.render.mixin"]._render_template_qweb(
                    prompt, record._name, record.ids
                )[record.id]
            )
        return html2plaintext(prompt)

    def _post_run_action_ai_run(self, result, eval_context, record):
        self.ensure_one()
        if self.ai_output_mode == "post_message" and record and record.exists():
            body = self._prepare_message_body(result)
            record.message_post(body=body)
        elif self.ai_output_mode == "update_record":
            if record and self.ai_update_record_field_id:
                if markdown and self.ai_update_record_field_id.ttype == "html":
                    value = self._prepare_message_body(result)
                else:
                    value = result
                record.write({self.ai_update_record_field_id.name: value})
        elif self.ai_output_mode == "store_variable":
            if self.ai_context_variable:
                eval_context[self.ai_context_variable] = result

    def _prepare_message_body(self, result):
        if markdown:
            return html_sanitize(markdown.markdown(result))
        return plaintext2html(result)
