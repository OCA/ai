# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The AI that reads the conversations: an AI connection of OCA/ai.

The module only calls ``generate_json`` with the instructions, the parts of the
request (texts and files, see ``text_part`` and ``data_part``) and the JSON
schema of the answer. The connection (``ai.connection``) tells the provider and
the model that answer. The schema goes with the instructions, and the answer is
validated by the module whatever the provider.
"""

import base64
import json
import logging
import re

_logger = logging.getLogger(__name__)

# Files the AI is given as files: the connection sends them to its provider.
PDF = "application/pdf"
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MEDIA_TYPES = frozenset({PDF}) | IMAGE_TYPES
# Answers of the providers that a later attempt may get right.
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
# An answer wrapped in a block of code (```json ... ```).
CODE_BLOCK = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
SCHEMA_INSTRUCTION = (
    "\n\nAnswer only with one JSON object, without any other text, that "
    "follows this JSON schema:\n{schema}"
)


class AIError(Exception):
    """A failed call. ``retryable`` tells whether a later attempt may succeed."""

    def __init__(self, message, retryable=True):
        super().__init__(message)
        self.retryable = retryable


def text_part(text):
    """A text of the request."""
    return {"text": text}


def data_part(mimetype, data, filename=None):
    """A file of the request, read by the AI itself (see ``MEDIA_TYPES``)."""
    return {"mimetype": mimetype, "data": data, "filename": filename}


class AIClient:
    """Ask an AI connection for the JSON answers of the module."""

    #: Types of file the AI is given as files, among ``MEDIA_TYPES``.
    native_types = MEDIA_TYPES

    def __init__(self, connection):
        if not connection:
            raise AIError(
                "No AI connection is set in the settings of the company.",
                retryable=False,
            )
        self.connection = connection.sudo()
        self.label = self.connection.name
        self.model = self.connection.model or ""

    def __repr__(self):
        return f"<{type(self).__name__} {self.label} model={self.model}>"

    def generate_json(self, system_instruction, parts, response_schema):
        """Ask for a JSON answer that follows ``response_schema``.

        :param parts: the texts and files of the request, see ``text_part``
            and ``data_part``.
        :return: ``(data, raw_text, tokens)``, the decoded answer, the answer
            as sent by the AI and the tokens the request spent.
        """
        messages = self._messages(system_instruction, parts, response_schema)
        try:
            content, prompt_tokens, completion_tokens, _iterations = (
                self.connection._run_ai(messages)
            )
        except Exception as error:  # pylint: disable=broad-except
            # The errors of each provider: only their kind, which never holds
            # the request nor the key.
            status = getattr(error, "status_code", None)
            raise AIError(
                f"The AI connection {self.label} failed "
                f"({type(error).__name__}{f' {status}' if status else ''}).",
                retryable=status is None or status in RETRYABLE_STATUS,
            ) from None
        raw_text = content or ""
        tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        _logger.info("AI connection %s answered (%s tokens)", self.label, tokens)
        return self._decode(raw_text), raw_text, tokens

    def _messages(self, system_instruction, parts, response_schema):
        """The messages of the request, as ``ai.connection`` takes them: the
        texts that precede a file go in its message, so that the AI reads the
        label of each file with it."""
        system = system_instruction + SCHEMA_INSTRUCTION.format(
            schema=json.dumps(response_schema, ensure_ascii=False)
        )
        messages = [{"role": "system", "content": system}]
        current = None
        for part in parts:
            if current is None or ("text" in part and current["files"]):
                current = {"role": "user", "content": "", "files": []}
                messages.append(current)
            if "text" in part:
                current["content"] = "\n\n".join(
                    filter(None, [current["content"], part["text"]])
                )
            else:
                current["files"].append(
                    {
                        "name": part.get("filename") or "file",
                        "content": base64.b64encode(part["data"]).decode(),
                        "mimetype": part["mimetype"],
                    }
                )
        for message in messages[1:]:
            if not message["files"]:
                del message["files"]
        return messages

    def _decode(self, raw_text):
        text = raw_text.strip()
        block = CODE_BLOCK.match(text)
        if block:
            text = block.group(1)
        try:
            data = json.loads(text)
        except ValueError:
            raise AIError(
                f"The answer of {self.label} does not follow the JSON format "
                "requested."
            ) from None
        if not isinstance(data, dict):
            raise AIError(f"The answer of {self.label} is not a JSON object.")
        return data
