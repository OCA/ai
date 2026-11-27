# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import fields, models

from odoo.addons.ai_connection.client import AiConnectionClient


class FakeMatcherClient(AiConnectionClient):
    response_queue = []
    last_messages = []

    def __init__(self, tools):
        super().__init__()
        self.tools = tools or []

    def handle_message(self, messages=None, **kwargs):
        type(self).last_messages.append(messages[-1] if messages else {})
        if type(self).response_queue:
            nxt = type(self).response_queue.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            content = nxt
        else:
            content = json.dumps(
                {
                    "pressure_bar": 120.0,
                    "motor_power_kw": 2.3,
                    "phase": "Single-Phase",
                    "has_detergent_tank": True,
                }
            )
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
        selection_add=[("fake_matcher", "Fake Matcher")],
        ondelete={"fake_matcher": "cascade"},
    )

    def _get_client_fake_matcher(self, tools):
        return FakeMatcherClient(tools)
