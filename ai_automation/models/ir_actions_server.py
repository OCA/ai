# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from lxml import etree

from odoo import api, fields, models

from odoo.addons.web_editor.models.ir_qweb_fields import html_to_text


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[("ai_oca", "AI OCA Action")], ondelete={"ai_oca": "cascade"}
    )
    ai_connection_id = fields.Many2one(
        "ai.connection", string="AI Connection", groups="base.group_system"
    )
    ai_tool_ids = fields.Many2many(
        "ai.tool",
        string="AI Tools",
        groups="base.group_system",
    )
    ai_prompt = fields.Html(string="AI Prompt", sanitize=False)
    mailing_model_real = fields.Char(compute="_compute_mailing_model_real")
    ai_result_action = fields.Selection(
        [
            ("post_message", "Post Message"),
            ("update_record", "Update Record"),
        ],
        string="AI Result Action",
    )
    ai_update_record_field_id = fields.Many2one(
        "ir.model.fields",
        string="AI Update Record Field",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['char', 'text'])]",
    )

    @api.depends("model_id")
    def _compute_mailing_model_real(self):
        for record in self:
            record.mailing_model_real = (
                record.model_id.model if record.model_id else False
            )

    def _run_action_ai_oca(self, eval_context=None):
        record = eval_context.get("record")
        result = self.ai_connection_id._run(
            self._get_ai_oca_prompt(record), tools=self.ai_tool_ids, record=record
        )
        self._post_run_action_ai_oca(result, record)

    def _post_run_action_ai_oca(self, result, record):
        if self.ai_result_action == "post_message":
            self.env["ai.tool"]._ai_post_message(result, record=record)
        elif (
            self.ai_result_action == "update_record"
            and record
            and self.ai_update_record_field_id
        ):
            record.write({self.ai_update_record_field_id.name: result})

    def _get_ai_oca_prompt(self, record):
        ai_prompt = self.ai_prompt
        if record:
            ai_prompt = str(
                self.env["mail.render.mixin"]._render_template_qweb(
                    self.ai_prompt, record and record._name, record and record.ids
                )[record.id]
            )
        return html_to_text(etree.fromstring("<t>" + ai_prompt + "</t>"))
