from odoo import fields, models

from odoo.addons.ai_connection.client import AiConnectionClient


class AiClientDemo(AiConnectionClient):
    def __init__(self, tools):
        super().__init__()
        self.tools = tools or []

    def handle_message(self, messages, **kwargs):
        last_message = messages[-1]
        return {
            "message": {
                "role": "assistant",
                "content": "This is a demo response to the prompt: "
                f"{last_message['content']}",
            },
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 3,
            },
        }


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[("demo", "Demo")],
        ondelete={"demo": "cascade"},
    )

    def _get_client_demo(self, tools):
        return AiClientDemo(tools)
