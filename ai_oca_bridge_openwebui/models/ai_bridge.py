# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    payload_type = fields.Selection(
        selection_add=[("openwebui", "OpenWebUI Chat")],
        ondelete={"openwebui": "set default"},
    )
    openwebui_model = fields.Char(string="OpenWebUI Model")
    openwebui_tool_ids = fields.Char(
        string="OpenWebUI Tool IDs",
        help="Comma-separated IDs, for example server:0.",
    )
    openwebui_system_prompt = fields.Text(string="System Prompt")
    openwebui_history_limit = fields.Integer(string="History Size", default=10)
    openwebui_timeout = fields.Integer(string="Timeout (s)", default=120)

    @api.onchange("payload_type")
    def _onchange_payload_type_openwebui(self):
        for record in self:
            if record.payload_type == "openwebui":
                record.usage = "chatter"
                record.result_kind = "immediate"
                record.result_type = "message"

    @api.constrains(
        "payload_type", "usage", "result_kind", "result_type", "openwebui_model"
    )
    def _check_openwebui_configuration(self):
        for record in self.filtered(lambda b: b.payload_type == "openwebui"):
            if record.usage != "chatter":
                raise ValidationError(_("An OpenWebUI bridge must use the 'Chatter' usage."))
            if record.result_kind != "immediate":
                raise ValidationError(_("An OpenWebUI bridge must use the 'Immediate' result kind."))
            if record.result_type != "message":
                raise ValidationError(_("An OpenWebUI bridge must use the 'Post a Message' result."))
            if not record.openwebui_model:
                raise ValidationError(_("The OpenWebUI model is required."))

    def _openwebui_tool_ids(self):
        self.ensure_one()
        return [x.strip() for x in (self.openwebui_tool_ids or "").split(",") if x.strip()]

    def _prepare_payload_openwebui(self, record=None, **kwargs):
        self.ensure_one()
        if record is None or not record:
            record = self.env["mail.message"].sudo().search(
                [("model", "=", "discuss.channel"), ("message_type", "=", "comment")],
                order="id desc", limit=1,
            )
        if record and record._name != "mail.message":
            raise ValueError(_("The record must be a mail.message instance."))
        messages = []
        system = self._openwebui_system_content(record)
        if system:
            messages.append({"role": "system", "content": system})
        if record:
            messages.extend(self._openwebui_history(record))
        payload = {"model": self.openwebui_model or "", "messages": messages, "stream": False}
        tool_ids = self._openwebui_tool_ids()
        if tool_ids:
            payload["tool_ids"] = tool_ids
            payload["params"] = {"function_calling": "legacy"}
        return payload

    def _openwebui_system_content(self, record):
        self.ensure_one()
        parts = [self.openwebui_system_prompt.strip()] if self.openwebui_system_prompt else []
        if record and record.model == "discuss.channel":
            channel = self.env["discuss.channel"].sudo().browse(record.res_id).exists()
            if channel:
                parts.append("Odoo channel: %s" % channel.display_name)
        return "\n\n".join(parts)

    def _openwebui_history(self, record):
        self.ensure_one()
        history = self.env["mail.message"].sudo().search(
            [("model", "=", record.model), ("res_id", "=", record.res_id),
             ("message_type", "=", "comment"), ("id", "<=", record.id)],
            order="id desc", limit=max(self.openwebui_history_limit or 1, 1),
        )
        result = []
        for message in reversed(history):
            text = tools.html2plaintext(message.body or "").strip()
            if text:
                is_ai = bool(message.author_id.user_ids.ai_bridge_id)
                result.append({"role": "assistant" if is_ai else "user", "content": text})
        return result
