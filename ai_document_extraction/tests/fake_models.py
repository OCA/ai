# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from odoo.addons.ai_connection.client import AiConnectionClient


class FakeExtractionClient(AiConnectionClient):
    last_messages = None
    response_queue = None

    def __init__(self, tools, default_response=None):
        self.tools = tools
        self.default_response = default_response or "{}"

    def handle_message(self, messages=None, **kwargs):
        FakeExtractionClient.last_messages = list(messages or [])
        if FakeExtractionClient.response_queue:
            content = FakeExtractionClient.response_queue.pop(0)
            if isinstance(content, Exception):
                raise content
        else:
            content = self.default_response
        return {
            "message": {
                "role": "assistant",
                "content": content,
            },
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
            },
        }


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[("fake_extraction", "Fake Extraction")],
        ondelete={"fake_extraction": "cascade"},
    )
    fake_response = fields.Text()

    def _get_client_fake_extraction(self, tools):
        return FakeExtractionClient(tools, default_response=self.fake_response)
