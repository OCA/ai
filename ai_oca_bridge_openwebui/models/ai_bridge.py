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
    openwebui_tool_ids = fields.Char(string="OpenWebUI Tool IDs", help="Comma-separated OpenWebUI tool identifiers.")
    openwebui_system_prompt = fields.Text(string="System Prompt")
    openwebui_web_search = fields.Boolean(string="Enable Web Search", help="Enable OpenWebUI's web search feature for this bridge.")
    openwebui_keep_chat = fields.Boolean(
        string="Keep OpenWebUI Conversation",
        default=True,
        help="Keep the OpenWebUI conversation so the user question and sources remain visible.",
    )
    openwebui_history_limit = fields.Integer(string="History Size", default=5)
    openwebui_timeout = fields.Integer(string="Timeout (s)", default=120)

    @api.onchange("payload_type")
    def _onchange_payload_type_openwebui(self):
        for record in self:
            if record.payload_type == "openwebui":
                record.usage = "chatter"
                record.result_kind = "immediate"
                record.result_type = "message"

    def _get_model_fields(self):
        """OpenWebUI selects the target from the triggering mail message.

        The base chatter bridge normally requires ``model_id``.  That is
        correct for a bridge attached to one model, but it prevents the
        catalog synchronization button from being used before a model is
        selected.  An empty model means all eligible mail.thread targets.
        """
        values = super()._get_model_fields()
        if self.payload_type == "openwebui":
            values["model_required"] = False
        return values

    @api.constrains("payload_type", "usage", "result_kind", "result_type")
    def _check_openwebui_configuration(self):
        for record in self.filtered(lambda bridge: bridge.payload_type == "openwebui"):
            if record.usage != "chatter":
                raise ValidationError(_("An OpenWebUI bridge must use the 'Chatter' usage."))
            if record.result_kind != "immediate":
                raise ValidationError(_("An OpenWebUI bridge must use the 'Immediate' result kind."))
            if record.result_type != "message":
                raise ValidationError(_("An OpenWebUI bridge must use the 'Post a Message' result."))

    def _openwebui_model_name(self):
        self.ensure_one()
        return self.openwebui_model_id.external_id if self.openwebui_model_id else (self.openwebui_model or "").strip()

    def _openwebui_check_model(self):
        self.ensure_one()
        if not self._openwebui_model_name():
            raise ValidationError(_("Select an OpenWebUI model before executing the bridge."))

    def _openwebui_tool_ids(self):
        self.ensure_one()
        selected = self.openwebui_tool_record_ids.filtered("active").mapped("external_id")
        return selected or [value.strip() for value in (self.openwebui_tool_ids or "").split(",") if value.strip()]

    def _openwebui_target_matches(self, message):
        """Return whether *message* is an eligible invocation for this bridge.

        The bridge is attached to the ``mail.message`` event, not directly to
        a Discuss channel or an Odoo document.  Keeping this decision in one
        method makes the same bridge work for Discuss conversations, tasks,
        notes and any other ``mail.thread`` model, while still allowing an
        optional model restriction in the bridge configuration.
        """
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
        # The base bridge computes ``sample_payload`` while the form is being
        # created.  At that point no catalog model may have been selected yet;
        # model validation belongs to a real execution, not to form creation.
        if not self._openwebui_model_name() and self.env.context.get("sample_payload"):
            return {"model": "", "messages": [], "stream": False}
        self._openwebui_check_model()
        if not record:
            domain = [("message_type", "=", "comment")]
            if self.model_id:
                domain.append(("model", "=", self.model_id.model))
            record = self.env["mail.message"].sudo().search(domain, order="id desc", limit=1)
        if record and record._name != "mail.message":
            raise ValueError(_("The record must be a mail.message instance."))
        if record and not self._openwebui_target_matches(record):
            raise ValidationError(_("The message is not an eligible target for this OpenWebUI bridge."))
        messages = []
        system = self._openwebui_system_content(record)
        if system:
            messages.append({"role": "system", "content": system})
        if record:
            messages.extend(self._openwebui_history(record))
            messages.append({"role": "user", "content": self._openwebui_message_content(record)})
        payload = {"model": self._openwebui_model_name(), "messages": messages, "stream": False}
        if self.openwebui_web_search:
            payload["features"] = {"web_search": True}
        tool_ids = self._openwebui_tool_ids()
        if tool_ids:
            payload["tool_ids"] = tool_ids
            payload["params"] = {"function_calling": "legacy"}
        return payload

    def _openwebui_system_content(self, record):
        self.ensure_one()
        parts = [self.openwebui_system_prompt.strip()] if self.openwebui_system_prompt else []
        parts.append(_("The current Odoo record context below is authoritative. Linked partner/contact references in a mention are not the target record; do not follow them instead of the current record. Internal Odoo references are context only, not sources and must never be cited as an answer. For current or recent events, use web search when enabled; otherwise state that live web access is unavailable."))
        if record and record.model and record.res_id:
            parts.append(self._openwebui_record_context(record))
        return "\n\n".join(parts)

    def _openwebui_record_context(self, message):
        """Build explicit, model-independent context for the current chatter.

        The previous implementation only exposed the display name and the
        free-form message history.  That made dates, authors and fields such
        as a task description unavailable to the assistant.  Keep this
        deliberately conservative so the bridge works for every mail.thread
        model without serialising an entire Odoo record.
        """
        self.ensure_one()
        try:
            target = self.env[message.model].sudo().browse(message.res_id).exists()
        except KeyError:
            target = self.env["mail.thread"].browse()
        if not target:
            return _("Current Odoo record: %(model)s, ID %(res_id)s (record not found)") % {
                "model": message.model,
                "res_id": message.res_id,
            }
        lines = [
            "CURRENT ODOO RECORD (authoritative target)",
            f"- Model: {message.model}",
            f"- ID: {target.id}",
            f"- Name: {target.display_name}",
        ]
        for field_name, label in (("description", "Description"), ("name", "Name")):
            if field_name not in target._fields or field_name == "name":
                continue
            value = target[field_name]
            if value:
                text = tools.html2plaintext(value).strip() if isinstance(value, str) else str(value)
                lines.append(f"- {label}: {text}")
            else:
                lines.append(f"- {label}: (empty)")
        for field_name, label in (("create_date", "Created"), ("write_date", "Last modified")):
            if field_name in target._fields and target[field_name]:
                lines.append(f"- {label}: {target[field_name]}")
        lines.append(
            "- The following chatter history belongs to this record; use its dates and authors when answering questions about notes."
        )
        return "\n".join(lines)

    def _openwebui_history(self, record):
        self.ensure_one()
        exchange_limit = max(self.openwebui_history_limit or 1, 1)
        history = self.env["mail.message"].sudo().search([
            ("model", "=", record.model), ("res_id", "=", record.res_id),
            ("message_type", "=", "comment"), ("id", "<", record.id),
        ], order="id desc", limit=max(exchange_limit * 2 + 2, 1))
        result = []
        for message in reversed(history):
            text = tools.html2plaintext(message.body or "").strip()
            if text:
                author = message.author_id.display_name or _("Unknown author")
                message_date = message.date or message.create_date or _("unknown date")
                content = (
                    f"[Odoo chatter note | id={message.id} | date={message_date} | author={author}]\n"
                    f"{text}"
                )
                result.append({"role": "assistant" if message.author_id.user_ids.filtered("ai_bridge_id") else "user", "content": content})
        user_indexes = [index for index, message in enumerate(result) if message["role"] == "user"]
        if len(user_indexes) > exchange_limit:
            result = result[user_indexes[-exchange_limit]:]
            if result and result[0]["role"] == "assistant":
                result = result[1:]
        return result
