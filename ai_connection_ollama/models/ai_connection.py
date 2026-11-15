# Copyright 2026 SDi - Angel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

import ollama

from odoo import fields, models

from odoo.addons.ai_connection.client import AiConnectionClient


class OllamaClient(AiConnectionClient):
    def __init__(self, tools, url, model, api_key=None, options=None):
        host = url or "http://localhost:11434"
        kwargs = {}
        if api_key:
            kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}
        self._client = ollama.Client(host=host, **kwargs)
        self.model = model
        self.options = options or {}
        self.tool_definition = []
        for tool in tools or []:
            definition = tool._get_tool_definition()
            self.tool_definition.append(
                {
                    "type": "function",
                    "function": {
                        "name": definition["name"],
                        "description": definition["description"],
                        "parameters": definition["inputSchema"],
                    },
                }
            )

    def handle_message(self, messages=None, **kwargs):
        messages = [self._adapt_message(msg) for msg in (messages or [])]
        response = self._client.chat(
            model=self.model,
            messages=messages,
            tools=self.tool_definition or None,
            options=self.options,
            stream=False,
        )
        msg = response.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        return {
            "message": msg,
            "tool_calls": [
                {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                }
                for tc in tool_calls
            ],
            "usage": {
                "prompt_tokens": response.get("prompt_eval_count", 0),
                "completion_tokens": response.get("eval_count", 0),
            },
        }

    def _adapt_message(self, msg):
        msg = dict(msg)
        files = msg.pop("files", None)
        if files:
            images = []
            text_parts = []
            for f in files:
                if f.get("mimetype", "").startswith("image/") and f.get("content"):
                    images.append(f["content"])
                elif f.get("content"):
                    text_parts.append(
                        f"\n\n[file: {f.get('name', 'unknown')}]\n"
                        f"{f['content'][:3000]}"
                    )
            if images:
                msg["images"] = images
            if text_parts:
                msg["content"] = (msg.get("content") or "") + "\n".join(text_parts)
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                if isinstance(fn.get("arguments"), str):
                    try:
                        fn["arguments"] = json.loads(fn["arguments"])
                    except (json.JSONDecodeError, TypeError):
                        continue
        return msg


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[("ollama", "Ollama")],
        ondelete={"ollama": "cascade"},
    )
    api_key = fields.Char(groups="base.group_system")
    ollama_options = fields.Json(
        help="Additional Ollama options like num_ctx, num_predict, etc.",
    )

    def _get_client_ollama(self, tools):
        return OllamaClient(
            tools=tools,
            url=self.url,
            model=self.model,
            api_key=self.api_key,
            options=self.ollama_options,
        )
