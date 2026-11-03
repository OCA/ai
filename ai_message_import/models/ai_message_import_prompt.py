# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from ..services.ai_client import AIError
from ..services.prompts import (
    PROMPT_EXTRACTION,
    PROMPT_PRODUCT_CHOICE,
    document_type_code,
)


class AiMessageImportPrompt(models.Model):
    """An instruction for the AI.

    The module only knows which prompts it needs and their placeholders: each
    module creates its own, without text (``data/ai_message_import_prompt.xml``).
    Their text is written here, or by a module (as the custom one of Binhex),
    so it can change without changing the code.
    """

    _name = "ai.message.import.prompt"
    _description = "AI Prompt"
    _order = "code"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        index=True,
        help="Prompt the module asks for: 'extraction' (reading the "
        "conversations, with {types} and {version}), 'product_choice' (choosing "
        "the products of the lines, with {role} and {lang}) or "
        "'document_type.<type>' (when a document is of that type, e.g. "
        "document_type.purchase).",
    )
    content = fields.Text(
        help="Text of the prompt. Until it is written, the module cannot use it."
    )

    _sql_constraints = [
        ("code_uniq", "unique(code)", "There is already a prompt with this code."),
    ]

    @api.model
    def _required_codes(self):
        """The prompts the installed modules need: the core ones and the
        description of each document type."""
        types = self.env["ai.message.import.document"]._document_types()
        return [PROMPT_EXTRACTION, PROMPT_PRODUCT_CHOICE] + [
            document_type_code(key) for key in types
        ]

    @api.model
    def _missing_codes(self):
        """The prompts the installed modules need and nobody wrote yet."""
        written = {
            prompt.code
            for prompt in self.sudo().search([("content", "!=", False)])
            if prompt.content.strip()
        }
        return [code for code in self._required_codes() if code not in written]

    @api.model
    def _content(self, code):
        """The text of the prompt ``code``.

        :raise AIError: when it is not configured, which no retry solves.
        """
        prompt = self.sudo().search([("code", "=", code)], limit=1)
        if not (prompt.content or "").strip():
            raise AIError(
                self.env._(
                    "The AI prompt %(code)s is not configured: write it in "
                    "Configuration > AI prompts.",
                    code=code,
                ),
                retryable=False,
            )
        return prompt.content
