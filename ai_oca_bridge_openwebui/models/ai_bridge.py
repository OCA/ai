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
    openwebui_model = fields.Char(string="OpenWebUI Model (legacy)")
    openwebui_tool_ids = fields.Char(
        string="OpenWebUI Tool IDs",
        help="Comma-separated OpenWebUI tool identifiers.",
    )
    openwebui_system_prompt = fields.Text(string="System Prompt")
    openwebui_history_limit = fields.Integer(string="History Size", default=5)
    openwebui_timeout = fields.Integer(string="Timeout (s)", default=120)

    @api.onchange("payload_type")
    def _onchange_payload_type_openwebui(self):
        for record in self:
            if record.payload_type == "openwebui":
                record.usage = "chatter"
                record.result_kind = "immediate"
                record.result_type = "message"

    @api.constrains("payload_type", "usage", "result_kind", "result_type")
    def _check_openwebui_configuration(self):
        for record in self.filtered(lambda bridge: bridge.payload_type == "openwebui"):
            if record.usage != "chatter":
                raise ValidationError(
                    _("An OpenWebUI bridge must use the " "'Chatter' usage.")
                )
            if record.result_kind != "immediate":
                raise ValidationError(
                    _("An OpenWebUI bridge must use the " "'Immediate' result kind.")
                )
            if record.result_type != "message":
                raise ValidationError(
                    _("An OpenWebUI bridge must use the 'Post a Message' result.")
                )

    def _openwebui_model_name(self):
        self.ensure_one()
        return (
            self.openwebui_model_id.external_id
            if self.openwebui_model_id
            else (self.openwebui_model or "").strip()
        )

    def _openwebui_check_model(self):
        self.ensure_one()
        if not self._openwebui_model_name():
            raise ValidationError(
                _("Select an OpenWebUI model before executing the bridge.")
            )

    def _openwebui_tool_ids(self):
        self.ensure_one()
        selected = self.openwebui_tool_record_ids.filtered("active").mapped(
            "external_id"
        )
        return selected or [
            value.strip()
            for value in (self.openwebui_tool_ids or "").split(",")
            if value.strip()
        ]

    def _openwebui_target_matches(self, message):
        self.ensure_one()
        return bool(
            message
            and message._name == "mail.message"
            and (not self.model_id or self.model_id.model == message.model)
        )

    def _prepare_payload_openwebui(self, record=None, **kwargs):
        self.ensure_one()
        self._openwebui_check_model()
        if not record:
            domain = [("message_type", "=", "comment")]
            if self.model_id:
                domain.append(("model", "=", self.model_id.model))
            record = (
                self.env["mail.message"].sudo().search(domain, order="id desc", limit=1)
            )
        if record and record._name != "mail.message":
            raise ValueError(_("The record must be a mail.message instance."))
        messages = []
        system = self._openwebui_system_content(record)
        if system:
            messages.append({"role": "system", "content": system})
        if record:
            messages.extend(self._openwebui_history(record))
            messages.append(
                {
                    "role": "user",
                    "content": self._openwebui_message_content(record),
                }
            )
        payload = {
            "model": self._openwebui_model_name(),
            "messages": messages,
            "stream": False,
        }
        tool_ids = self._openwebui_tool_ids()
        if tool_ids:
            payload["tool_ids"] = tool_ids
            payload["params"] = {"function_calling": "legacy"}
        return payload

    def _openwebui_system_content(self, record):
        self.ensure_one()
        parts = (
            [self.openwebui_system_prompt.strip()]
            if self.openwebui_system_prompt
            else []
        )
        if record and record.model and record.res_id:
            try:
                target = self.env[record.model].sudo().browse(record.res_id).exists()
            except KeyError:
                target = self.env["mail.thread"].browse()
            if target:
                parts.append(
                    f"Odoo record: {target.display_name} "
                    f"({record.model}, ID {target.id})"
                )
        return "\n\n".join(parts)

    def _openwebui_history(self, record):
        """Return the last configured number of complete conversation exchanges."""
        self.ensure_one()
        exchange_limit = max(self.openwebui_history_limit or 1, 1)
        history = (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", record.model),
                    ("res_id", "=", record.res_id),
                    ("message_type", "=", "comment"),
                    ("id", "<", record.id),
                ],
                order="id desc",
                limit=max(exchange_limit * 2 + 1, 1),
            )
        )
        result = []
        for message in reversed(history):
            text = tools.html2plaintext(message.body or "").strip()
            if not text:
                continue
            result.append(
                {
                    "role": (
                        "assistant"
                        if message.author_id.user_ids.filtered("ai_bridge_id")
                        else "user"
                    ),
                    "content": text,
                }
            )
        user_indexes = [
            index for index, message in enumerate(result) if message["role"] == "user"
        ]
        if len(user_indexes) > exchange_limit:
            result = result[user_indexes[-exchange_limit] :]
        return result
