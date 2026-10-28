# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import time
import traceback
import uuid

import requests

from odoo import _, models
from odoo.tools.mail import html_sanitize, plaintext2html

try:
    import markdown
except ImportError:
    markdown = None

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
                _("The chatter target could not be found: %(model)s, %(res_id)s")
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
            response = self._openwebui_execute_agentic(payload)
            self.result = response.get("raw", "")
            self.state = "done"
            return self._process_response(response["completion"])
        except Exception:
            _logger.exception("OpenWebUI bridge %s failed", bridge.display_name)
            self.state = "error"
            self.error = traceback.format_exc()
            self._openwebui_stop_typing()
            return {}

    def _openwebui_base_url(self):
        self.ensure_one()
        return self.ai_bridge_id.url.split("/api/", 1)[0].rstrip("/")

    def _openwebui_request(self, method, path, **kwargs):
        self.ensure_one()
        response = requests.request(
            method,
            f"{self._openwebui_base_url()}{path}",
            auth=self._get_auth(),
            headers=self._get_headers(),
            timeout=self.ai_bridge_id.openwebui_timeout or 120,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def _openwebui_chat_payload(self, payload, chat_id, assistant_id):
        self.ensure_one()
        request_payload = {
            "model": payload["model"],
            "messages": payload.get("messages") or [],
            "stream": True,
            "chat_id": chat_id,
            "id": assistant_id,
            "session_id": f"odoo-{uuid.uuid4()}",
            "features": {
                "web_search": bool(self.ai_bridge_id.openwebui_web_search),
                "code_interpreter": False,
                "image_generation": False,
                "memory": False,
            },
            "background_tasks": {
                "title_generation": False,
                "tags_generation": False,
                "follow_up_generation": False,
            },
        }
        if payload.get("tool_ids"):
            request_payload["tool_ids"] = payload["tool_ids"]
        return request_payload

    def _openwebui_chat_title(self):
        self.ensure_one()
        message = self._openwebui_message_record()
        if message and message.model == "discuss.channel" and message.res_id:
            channel = self.env["discuss.channel"].sudo().browse(message.res_id).exists()
            if channel:
                return channel.display_name or channel.name or _("Odoo Discuss")
        return _("Odoo Discuss")

    def _openwebui_create_chat(self, payload, assistant_id):
        self.ensure_one()
        timestamp = int(time.time())
        messages = payload.get("messages") or []
        user_content = next(
            (
                message.get("content", "")
                for message in reversed(messages)
                if message.get("role") == "user"
            ),
            "",
        )
        user_id = str(uuid.uuid4())
        model_name = payload["model"]
        chat = {
            "title": self._openwebui_chat_title(),
            "models": [model_name],
            "history": {
                "currentId": assistant_id,
                "messages": {
                    user_id: {
                        "id": user_id,
                        "role": "user",
                        "content": user_content,
                        "timestamp": timestamp,
                        "models": [model_name],
                        "childrenIds": [assistant_id],
                    },
                    assistant_id: {
                        "id": assistant_id,
                        "role": "assistant",
                        "content": "",
                        "parentId": user_id,
                        "childrenIds": [],
                        "model": model_name,
                        "modelName": model_name,
                        "modelIdx": 0,
                        "done": False,
                        "timestamp": timestamp + 1,
                    },
                },
            },
        }
        response = self._openwebui_request(
            "POST", "/api/v1/chats/new", json={"chat": chat}
        )
        chat_id = response.json().get("id")
        if not chat_id:
            raise ValueError(_("OpenWebUI did not return a temporary chat ID."))
        return chat_id

    def _openwebui_poll_chat(self, chat_id):
        self.ensure_one()
        deadline = time.monotonic() + (self.ai_bridge_id.openwebui_timeout or 120)
        while time.monotonic() < deadline:
            task_data = (
                self._openwebui_request("GET", f"/api/tasks/chat/{chat_id}").json()
                or {}
            )
            if not task_data.get("task_ids"):
                return
            self._openwebui_sleep(1)
        raise TimeoutError(_("OpenWebUI did not finish the temporary chat in time."))

    def _openwebui_sleep(self, seconds):
        time.sleep(seconds)

    def _openwebui_read_chat(self, chat_id, assistant_id):
        self.ensure_one()
        data = self._openwebui_request("GET", f"/api/v1/chats/{chat_id}").json() or {}
        messages = data.get("chat", {}).get("history", {}).get("messages", {})
        assistant = messages.get(assistant_id)
        if not assistant:
            raise ValueError(_("OpenWebUI did not return the assistant message."))
        return {"choices": [{"message": assistant}]}

    def _openwebui_delete_chat(self, chat_id):
        self.ensure_one()
        try:
            self._openwebui_request("DELETE", f"/api/v1/chats/{chat_id}")
        except Exception:
            _logger.warning(
                "Unable to delete temporary OpenWebUI chat %s", chat_id, exc_info=True
            )

    def _openwebui_execute_agentic(self, payload):
        self.ensure_one()
        assistant_id = str(uuid.uuid4())
        chat_id = None
        try:
            chat_id = self._openwebui_create_chat(payload, assistant_id)
            request_payload = self._openwebui_chat_payload(
                payload, chat_id, assistant_id
            )
            response = self._openwebui_request(
                "POST", "/api/chat/completions", json=request_payload, stream=True
            )
            try:
                raw_response = response.text
            finally:
                response.close()
            self._openwebui_poll_chat(chat_id)
            completion = self._openwebui_read_chat(chat_id, assistant_id)
            return {"completion": completion, "raw": raw_response}
        finally:
            if chat_id and not self.ai_bridge_id.openwebui_keep_chat:
                self._openwebui_delete_chat(chat_id)

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
            target.with_context(skip_openwebui_bridge=True)
            .sudo()
            .message_post(**values)
        )
        return {"id": message.id}

    def _openwebui_response_content(self, message):
        content = message.get("content")
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
                and item.get("type") in ("text", "output_text")
            )
        return content

    def _openwebui_to_message(self, response):
        try:
            message = response["choices"][0]["message"]
            content = self._openwebui_response_content(message)
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError(
                _("Unexpected answer from OpenWebUI: %s", str(response)[:500])
            ) from error
        content = (content or "").strip()
        if not content:
            raise ValueError(_("OpenWebUI returned an empty answer."))
        if markdown:
            body = html_sanitize(
                markdown.markdown(content, extensions=["extra", "nl2br"])
            )
        else:
            body = plaintext2html(content)
        return {"body": body, "message_type": "comment"}
