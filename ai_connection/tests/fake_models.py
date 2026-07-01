import base64

from odoo import fields, models

from odoo.addons.ai_connection.client import AiConnectionClient


class AiClientDemo(AiConnectionClient):
    def __init__(self, tools):
        super().__init__()
        self.tools = tools or []

    def handle_message(self, messages, **kwargs):
        last_message = messages[-1]
        content = last_message["content"]
        if last_message.get("files"):
            content = base64.b64decode(last_message["files"][0]["content"]).decode(
                "utf-8"
            )
        if any(tool.name == content for tool in self.tools):
            return {
                "message": {
                    "role": "assistant",
                    "content": f"This is a demo response to the prompt: {content}",
                },
                "tool_calls": [
                    {
                        "name": content,
                        "arguments": {},
                    }
                ],
            }
        return {
            "message": {
                "role": "assistant",
                "content": "This is a demo response to the prompt: " f"{content}",
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
