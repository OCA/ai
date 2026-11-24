# Copyright 2026 Nimarosa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# Test-only extension, loaded with FakeModelLoader
# pylint: disable=consider-merging-classes-inherited

from odoo import fields, models

from odoo.addons.ai_connection.client import AiConnectionClient

CALLS = []


class AiClientUsageFake(AiConnectionClient):
    """Answers locally, reporting 1000 prompt and 500 completion tokens."""

    def handle_message(self, messages, **kwargs):
        content = messages[-1]["content"]
        CALLS.append(content)
        if content == "fail":
            raise ConnectionError("provider unreachable")
        return {
            "message": {"role": "assistant", "content": f"Answer to {content}"},
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[("usage_fake", "Usage Fake")],
        ondelete={"usage_fake": "cascade"},
    )

    def _get_client_usage_fake(self, tools):
        return AiClientUsageFake()
