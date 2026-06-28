# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

import openai

from odoo import fields, models

from odoo.addons.ai_connection.client import AiConnectionClient


class OpenaiClient(AiConnectionClient):
    def __init__(self, tools, url, model, api_key, temperature=None):
        params = {}
        if url:
            params["base_url"] = url
        if api_key:
            params["api_key"] = api_key
        self._client = openai.OpenAI(**params)
        self.model = model
        self.temperature = temperature
        self.tool_definition = []
        for tool in tools or []:
            definition = tool._get_tool_definition()
            input_schema = definition["inputSchema"]
            input_schema["additionalProperties"] = False
            self.tool_definition.append(
                {
                    "type": "function",
                    "function": {
                        "name": definition["name"],
                        "description": definition["description"],
                        "parameters": input_schema,
                    },
                }
            )

    def handle_message(self, messages=None, **kwargs):
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tool_definition or None,
            temperature=self.temperature,
        )
        response_message = response.choices[0].message
        return {
            "message": response_message.model_dump(),
            "tool_calls": [
                {
                    "name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments),
                    "id": tool_call.id,
                }
                for tool_call in response_message.tool_calls or []
            ],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        }


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[("openai", "OpenAI")], ondelete={"openai": "cascade"}
    )
    openai_api_key = fields.Char(groups="base.group_system")

    def _get_client_openai(self, tools):
        return OpenaiClient(
            tools, url=self.url, model=self.model, api_key=self.openai_api_key
        )
