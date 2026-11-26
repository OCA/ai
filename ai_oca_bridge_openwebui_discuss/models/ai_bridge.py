# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, models, tools
from odoo.exceptions import ValidationError


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    @api.onchange("payload_type", "usage")
    def _onchange_openwebui_chatter(self):
        for bridge in self:
            if bridge.payload_type == "openwebui" and bridge.usage == "chatter":
                bridge.result_kind = "immediate"
                bridge.result_type = "message"

    def _openwebui_target_matches(self, message):
        """Check whether a chatter message is an eligible bridge invocation."""
        self.ensure_one()
        return bool(
            message
            and message._name == "mail.message"
            and message.message_type == "comment"
            and message.model
            and message.res_id
            and (not self.model_id or self.model_id.model == message.model)
        )

    def _prepare_payload_openwebui(self, record=None, **kwargs):
        self.ensure_one()
        if self.env.context.get("sample_payload"):
            return {
                "model": self._openwebui_model_name() or "",
                "messages": [],
                "stream": False,
            }
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
        if record and not self._openwebui_target_matches(record):
            raise ValidationError(
                _("The message is not an eligible target for this OpenWebUI bridge.")
            )

        messages = []
        system = self._openwebui_system_content(record)
        if system:
            messages.append({"role": "system", "content": system})
        if record:
            messages.extend(self._openwebui_history(record))
            messages.append(
                {"role": "user", "content": self._openwebui_message_content(record)}
            )
        payload = {
            "model": self._openwebui_model_name(),
            "messages": messages,
            "stream": False,
        }
        if self.openwebui_web_search:
            payload["features"] = {"web_search": True}
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
        parts.append(
            _(
                "The current Odoo record context below is authoritative. "
                "Linked partner/contact references in a mention are not the "
                "target record. Internal Odoo references are context only, "
                "not sources. For current events, use web search when enabled; "
                "otherwise state that live web access is unavailable."
            )
        )
        if record and record.model and record.res_id:
            parts.append(self._openwebui_record_context(record))
        return "\n\n".join(parts)

    def _openwebui_record_context(self, message):
        self.ensure_one()
        try:
            target = self.env[message.model].sudo().browse(message.res_id).exists()
        except KeyError:
            target = self.env["mail.thread"].browse()
        if not target:
            return _("Current Odoo record: %(model)s, ID %(res_id)s (not found)") % {
                "model": message.model,
                "res_id": message.res_id,
            }
        lines = [
            "CURRENT ODOO RECORD (authoritative target)",
            f"- Model: {message.model}",
            f"- ID: {target.id}",
            f"- Name: {target.display_name}",
        ]
        if "description" in target._fields and target.description:
            lines.append(
                f"- Description: {tools.html2plaintext(target.description).strip()}"
            )
        for field_name, label in (
            ("create_date", "Created"),
            ("write_date", "Last modified"),
        ):
            if field_name in target._fields and target[field_name]:
                lines.append(f"- {label}: {target[field_name]}")
        lines.append("- The following chatter history belongs to this record.")
        return "\n".join(lines)

    def _openwebui_history(self, record):
        self.ensure_one()
        limit = max(self.openwebui_history_limit or 1, 1)
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
                limit=max(limit * 2 + 2, 1),
            )
        )
        result = []
        for message in reversed(history):
            text = tools.html2plaintext(message.body or "").strip()
            if text:
                author = message.author_id.display_name or _("Unknown author")
                date = message.date or message.create_date or _("unknown date")
                result.append(
                    {
                        "role": "assistant"
                        if message.author_id.user_ids.filtered("ai_bridge_id")
                        else "user",
                        "content": (
                            f"[Odoo chatter note | id={message.id} | date={date} "
                            f"| author={author}]\n{text}"
                        ),
                    }
                )
        user_indexes = [i for i, item in enumerate(result) if item["role"] == "user"]
        if len(user_indexes) > limit:
            result = result[user_indexes[-limit] :]
            if result and result[0]["role"] == "assistant":
                result = result[1:]
        return result
