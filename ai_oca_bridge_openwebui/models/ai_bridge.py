# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    payload_type = fields.Selection(
        selection_add=[("openwebui", "OpenWebUI Chat")],
        ondelete={"openwebui": "set default"},
    )
    openwebui_model = fields.Char(string="OpenWebUI Model (legacy)")
    openwebui_tool_ids = fields.Char(
        string="OpenWebUI Tool IDs", help="Comma-separated OpenWebUI tool identifiers."
    )
    openwebui_system_prompt = fields.Text(string="System Prompt")
    openwebui_web_search = fields.Boolean(
        string="Enable Web Search",
        help="Enable OpenWebUI's web search feature for chatter requests.",
    )
    openwebui_keep_chat = fields.Boolean(
        string="Keep OpenWebUI Conversation",
        default=True,
        help="Keep OpenWebUI conversations created by chatter integrations.",
    )
    openwebui_history_limit = fields.Integer(string="History Size", default=5)
    openwebui_timeout = fields.Integer(string="Timeout (s)", default=120)

    def _get_model_fields(self):
        """Model selection is optional; each integration defines its own target."""
        values = super()._get_model_fields()
        if self.payload_type == "openwebui":
            values["model_required"] = False
        return values

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

    def _prepare_payload_openwebui(self, **kwargs):
        """Return a harmless sample payload for the generic bridge form.

        Chatter and other integrations prepare their own contextual payloads
        in their respective addons. A generic OpenWebUI bridge must not infer
        a mail.message or silently send an incomplete request.
        """
        if self.env.context.get("sample_payload"):
            return {
                "model": self._openwebui_model_name() or "",
                "messages": [],
                "stream": False,
            }
        raise ValidationError(
            _(
                "An OpenWebUI usage-specific integration is required to "
                "execute this bridge."
            )
        )
