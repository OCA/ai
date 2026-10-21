# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import traceback

import requests

from odoo import _, models, tools

_logger = logging.getLogger(__name__)


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    def _execute(self, **kwargs):
        """Execute OpenWebUI bridges without adding OCA bridge metadata."""
        self.ensure_one()
        bridge = self.ai_bridge_id
        if bridge.payload_type != "openwebui":
            return super()._execute(**kwargs)
        try:
            record = self.env[self.sudo().model_id.model].browse(self.res_id).exists()
            payload = bridge._prepare_payload(
                record=record,
                res_id=self.res_id,
                model=self.sudo().model_id.model,
            )
            self.payload = payload
            if not self._openwebui_must_answer(record, payload):
                self.state = "done"
                self.result = "Ignored: there is nothing to answer."
                self._openwebui_stop_typing()
                return {}
            response = requests.post(
                bridge.url,
                json=payload,
                auth=self._get_auth(),
                headers=self._get_headers(),
                timeout=bridge.openwebui_timeout or 120,
            )
            self.result = response.text
            response.raise_for_status()
            self.state = "done"
            return self._process_response(response.json())
        except Exception:
            _logger.exception("OpenWebUI bridge %s failed", bridge.display_name)
            self.state = "error"
            self.error = traceback.format_exc()
            self._openwebui_stop_typing()

    def _openwebui_must_answer(self, record, payload):
        if not record or record._name != "mail.message" or record.message_type != "comment":
            return False
        messages = payload.get("messages") or []
        return bool(messages) and messages[-1]["role"] == "user"

    def _openwebui_stop_typing(self):
        if not self.chatter_user_id or not self.res_id:
            return
        try:
            message = self.env["mail.message"].sudo().browse(self.res_id).exists()
            if not message or message.model != "discuss.channel":
                return
            member = self.env["discuss.channel.member"].sudo().search(
                [("partner_id", "=", self.chatter_user_id.partner_id.id),
                 ("channel_id", "=", message.res_id)], limit=1,
            )
            member._notify_typing(is_typing=False)
        except Exception:
            _logger.exception("Unable to stop the typing indicator")

    def _process_response(self, response):
        if self.ai_bridge_id.payload_type == "openwebui":
            response = self._openwebui_to_message(response)
        return super()._process_response(response)

    def _openwebui_to_message(self, response):
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError(
                _("Unexpected answer from OpenWebUI: %s", str(response)[:500])
            ) from error
        content = (content or "").strip()
        if not content:
            raise ValueError(_("OpenWebUI returned an empty answer."))
        return {"body": tools.plaintext2html(content)}
