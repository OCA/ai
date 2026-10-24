# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import traceback

import requests

from odoo import _, models, tools

_logger = logging.getLogger(__name__)


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    def _openwebui_message_record(self):
        self.ensure_one()
        return self.env["mail.message"].sudo().browse(self.res_id).exists()

    def _get_channel(self):
        self.ensure_one()
        if self.ai_bridge_id.payload_type != "openwebui":
            return super()._get_channel()
        message = self._openwebui_message_record()
        if not message:
            raise ValueError(_("The triggering mail message could not be found."))
        if not message.model or not message.res_id:
            raise ValueError(_("The triggering message has no chatter target."))
        try:
            target_model = self.env[message.model]
        except KeyError as error:
            raise ValueError(_("Unknown chatter model: %s") % message.model) from error
        target = target_model.sudo().browse(message.res_id).exists()
        if not target:
            raise ValueError(
                _("The chatter target could not be found: " "%(model)s, %(res_id)s")
                % {"model": message.model, "res_id": message.res_id}
            )
        return target

    def _execute(self, **kwargs):
        self.ensure_one()
        bridge = self.ai_bridge_id
        if bridge.payload_type != "openwebui":
            return super()._execute(**kwargs)
        try:
            record = self._openwebui_message_record()
            if not bridge._openwebui_target_matches(record):
                self.state = "done"
                self.result = "Ignored: bridge model does not match the message model."
                return {}
            payload = bridge._prepare_payload(
                record=record,
                res_id=record.res_id if record else False,
                model=record.model if record else False,
                **kwargs,
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
            return {}

    def _openwebui_must_answer(self, record, payload):
        if (
            not record
            or record._name != "mail.message"
            or record.message_type != "comment"
        ):
            return False
        messages = payload.get("messages") or []
        return bool(messages) and messages[-1].get("role") == "user"

    def _openwebui_stop_typing(self):
        if not self.chatter_user_id or not self.res_id:
            return
        try:
            message = self._openwebui_message_record()
            if not message or message.model != "discuss.channel":
                return
            member = (
                self.env["discuss.channel.member"]
                .sudo()
                .search(
                    [
                        ("partner_id", "=", self.chatter_user_id.partner_id.id),
                        ("channel_id", "=", message.res_id),
                    ],
                    limit=1,
                )
            )
            if member:
                member._notify_typing(is_typing=False)
        except Exception:
            _logger.exception("Unable to stop the typing indicator")

    def _process_response(self, response):
        if self.ai_bridge_id.payload_type != "openwebui":
            return super()._process_response(response)
        values = self._openwebui_to_message(response)
        target = self._get_channel()
        self._openwebui_stop_typing()
        author = self.chatter_user_id or self.ai_bridge_id.user_id
        if not author or not author.partner_id:
            raise ValueError(_("The OpenWebUI bridge has no author user."))
        values["author_id"] = author.partner_id.id
        if target._name == "discuss.channel":
            values["partner_ids"] = [
                partner_id
                for partner_id in target.channel_member_ids.sudo().partner_id.ids
                if partner_id != author.partner_id.id
            ]
        message = (
            target.with_context(
                skip_openwebui_bridge=True,
            )
            .sudo()
            .message_post(**values)
        )
        return {"id": message.id}

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
        return {
            "body": tools.plaintext2html(content),
            "message_type": "comment",
        }
