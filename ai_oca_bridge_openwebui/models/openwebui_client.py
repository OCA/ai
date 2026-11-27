# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


# pylint: disable=consider-merging-classes-inherited
class AiBridge(models.Model):
    _inherit = "ai.bridge"

    @api.constrains("payload_type", "usage", "result_kind", "result_type")
    def _check_openwebui_configuration(self):
        """Validate the common transport settings; each addon owns its usage."""
        expected_result_types = {
            "none": "none",
            "chatter": "message",
            "project_task": "none",
            "web_editor": "none",
        }
        for bridge in self.filtered(lambda item: item.payload_type == "openwebui"):
            if bridge.result_kind != "immediate":
                raise ValidationError(
                    _("OpenWebUI integrations require an immediate result.")
                )
            expected = expected_result_types.get(bridge.usage)
            if expected is None:
                raise ValidationError(
                    _("Select an OpenWebUI integration usage before saving the bridge.")
                )
            if bridge.result_type != expected:
                raise ValidationError(
                    _(
                        "The result type for usage '%(usage)s' must be '%(result)s'.",
                        usage=bridge.usage,
                        result=expected,
                    )
                )

    def _openwebui_request(self, method, path, **kwargs):
        """Make an authenticated server-side request to this bridge's OpenWebUI."""
        self.ensure_one()
        if not self.url:
            raise UserError(_("The OpenWebUI URL is not configured on the bridge."))
        base_url = self.url.split("/api/", 1)[0].rstrip("/")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        auth = None
        if self.auth_type == "token":
            if not self.auth_token:
                raise UserError(_("The OpenWebUI API token is missing."))
            headers["Authorization"] = f"Bearer {self.auth_token}"
        elif self.auth_type == "basic":
            if not self.auth_username or not self.auth_password:
                raise UserError(_("OpenWebUI basic authentication is incomplete."))
            auth = (self.auth_username, self.auth_password)
        elif self.auth_type != "none":
            raise UserError(_("The OpenWebUI authentication type is unsupported."))

        response = requests.request(
            method,
            f"{base_url}{path}",
            headers=headers,
            auth=auth,
            timeout=self.openwebui_timeout or 120,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def _openwebui_chat_completion(self, messages):
        """Return one non-streaming OpenWebUI completion as plain text.

        This shared path is intended for synchronous UI integrations such as
        the HTML editor and the project-task description wizard. Chatter's
        agentic/tool flow remains in its dedicated addon.
        """
        self.ensure_one()
        self._openwebui_check_model()
        request_messages = [dict(message) for message in (messages or [])]
        if self.openwebui_system_prompt:
            request_messages.insert(
                0,
                {"role": "system", "content": self.openwebui_system_prompt.strip()},
            )
        payload = {
            "model": self._openwebui_model_name(),
            "messages": request_messages,
            "stream": False,
        }
        try:
            data = self._openwebui_request(
                "POST", "/api/chat/completions", json=payload
            ).json()
            content = data["choices"][0]["message"]["content"]
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            _logger.exception("OpenWebUI text completion failed for bridge %s", self.id)
            raise UserError(
                _(
                    "OpenWebUI could not generate a response. Check the "
                    "bridge configuration and try again."
                )
            ) from error

        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
                and item.get("type") in ("text", "output_text")
            )
        if not isinstance(content, str) or not content.strip():
            raise UserError(_("OpenWebUI returned an empty response."))
        return content.strip()
