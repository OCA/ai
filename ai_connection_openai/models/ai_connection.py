# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json

import openai

from odoo import fields, models

from odoo.addons.ai_connection.client import AiConnectionClient


class OpenaiClient(AiConnectionClient):
    def __init__(
        self,
        tools,
        url,
        model,
        api_key,
        temperature=None,
        max_completion_tokens=None,
        timeout=None,
    ):
        params = {}
        if url:
            params["base_url"] = url
        if api_key:
            params["api_key"] = api_key
        if timeout:
            params["timeout"] = timeout
        self._client = openai.OpenAI(**params)
        self.model = model
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
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

    def _get_messages(self, messages):
        return [self._get_message(message) for message in messages]

    def _get_message(self, message):
        if not message.get("files"):
            return message
        new_message = message.copy()
        files = new_message.pop("files")
        content = new_message.get("content")
        new_message["content"] = []
        if content:
            new_message["content"].append({"type": "text", "text": content})
        for file in files:
            if file["mimetype"].startswith("text/"):
                new_message["content"].append(
                    {
                        "type": "text",
                        "text": base64.b64decode(file["content"]).decode("utf-8"),
                    }
                )
            elif file["mimetype"].startswith("image/"):
                new_message["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{file['mimetype']};base64,{file['content']}"
                        },
                    }
                )
            else:
                # This part works should work with OpenAI, but some similar sistems
                # like vLLM do not support it yet
                new_message["content"].append(
                    {
                        "type": "file",
                        "file": {
                            "filename": file["name"],
                            "file_data": file["content"],
                        },
                    }
                )
        return new_message

    def handle_message(self, messages=None, **kwargs):
        params = {}
        if self.max_completion_tokens:
            params["max_completion_tokens"] = self.max_completion_tokens
        response = self._client.chat.completions.create(
            model=self.model,
            messages=self._get_messages(messages),
            tools=self.tool_definition or None,
            temperature=self.temperature,
            **params,
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
    openai_max_completion_tokens = fields.Integer(
        string="Max Completion Tokens",
        help="Upper bound of tokens generated per request, reasoning included. "
        "Leave empty to use the server default.",
    )
    openai_timeout = fields.Float(
        string="Timeout",
        help="Timeout of each request, in seconds. "
        "Leave empty to use the client default.",
    )

    def _get_client_openai(self, tools):
        return OpenaiClient(
            tools,
            url=self.url,
            model=self.model,
            api_key=self.openai_api_key,
            temperature=self.temperature,
            max_completion_tokens=self.openai_max_completion_tokens,
            timeout=self.openai_timeout,
        )
