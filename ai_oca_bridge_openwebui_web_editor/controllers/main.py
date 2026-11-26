# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.html_editor.controllers.main import HTML_Editor

_logger = logging.getLogger(__name__)
_MAX_MESSAGES = 40
_MAX_CONTEXT_LENGTH = 100_000


class HtmlEditorOpenWebUI(HTML_Editor):
    @http.route()
    def generate_text(self, prompt, conversation_history):
        """Keep Odoo's editor route and response contract, swap only the LLM call."""
        if not request.env.user._is_internal():
            raise AccessError(_("Only internal users can use AI text generation."))
        if not isinstance(prompt, str) or not prompt.strip():
            raise UserError(_("Enter a prompt before generating text."))
        if (
            not isinstance(conversation_history, list)
            or len(conversation_history) > _MAX_MESSAGES
        ):
            raise UserError(_("The AI conversation is invalid or too long."))

        messages = []
        total_length = 0
        for item in conversation_history:
            if (
                not isinstance(item, dict)
                or item.get("role") not in {"system", "user", "assistant"}
                or not isinstance(item.get("content"), str)
            ):
                raise UserError(
                    _("The AI conversation contains an unsupported message.")
                )
            total_length += len(item["content"])
            messages.append({"role": item["role"], "content": item["content"]})
        total_length += len(prompt)
        if total_length > _MAX_CONTEXT_LENGTH:
            raise UserError(_("The selected text and conversation are too long."))
        messages.append({"role": "user", "content": prompt})

        bridges = (
            request.env["ai.bridge"]
            .sudo()
            .search(
                [
                    ("active", "=", True),
                    ("payload_type", "=", "openwebui"),
                    ("usage", "=", "web_editor"),
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", request.env.company.id),
                ],
                order="sequence, id",
                limit=2,
            )
        )
        if not bridges:
            # Do not silently send the editor contents to Odoo IAP when this
            # integration is installed but not configured.
            raise UserError(
                _("Configure one active OpenWebUI bridge with the 'HTML Editor' usage.")
            )
        if len(bridges) != 1:
            raise UserError(
                _(
                    "There must be exactly one active OpenWebUI bridge "
                    "for the HTML editor."
                )
            )
        bridge = bridges[0]
        if bridge.model_id:
            raise UserError(
                _(
                    "The HTML Editor bridge must not be restricted to an "
                    "Odoo business model."
                )
            )
        if bridge.group_ids and not (
            set(request.env.user.groups_id.ids) & set(bridge.group_ids.ids)
        ):
            raise AccessError(_("You are not allowed to use the configured AI bridge."))
        bridge._openwebui_check_model()
        try:
            return bridge._openwebui_chat_completion(messages)
        except UserError:
            raise
        except Exception as error:
            _logger.exception("Unexpected OpenWebUI HTML editor failure")
            raise UserError(
                _(
                    "OpenWebUI could not generate a response. Try again or "
                    "contact an administrator."
                )
            ) from error
