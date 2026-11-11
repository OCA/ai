# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

import ollama

from odoo import fields, models


class AiConnection(models.Model):
    _name = "ai.connection"
    _description = "AI Connection"

    name = fields.Char(required=True)
    kind = fields.Selection([("ollama", "Ollama")], required=True, default="ollama")
    active = fields.Boolean(default=True)
    url = fields.Char(groups="base.group_system")
    model = fields.Char(groups="base.group_system")

    def _run(self, prompt, tools=None, record=None):
        return getattr(self, f"_run_{self.kind}")(prompt, tools=tools, record=record)

    def _run_ollama(self, prompt, tools=None, messages=None, record=None):
        tool_definition = []
        for tool in tools or []:
            definition = tool._get_tool_definition()
            input_schema = definition["inputSchema"]
            input_schema["additionalProperties"] = False
            tool_definition.append(
                {
                    "type": "function",
                    "function": {
                        "name": definition["name"],
                        "description": definition["description"],
                        "parameters": input_schema,
                    },
                }
            )
        ollama_client = ollama.Client(**self._get_ollama_client_parameters())
        if messages is None:
            messages = []
        messages.append({"role": "user", "content": prompt})
        while True:
            response = ollama_client.chat(
                model=self.model,
                messages=messages,
                tools=tool_definition,
            )
            if not response.message.tool_calls:
                return response.message.content
            messages.append(response.message)
            for call in response.message.tool_calls:
                function_name = call.function.name
                tool = tools.filtered(lambda t, name=function_name: t.name == name)
                tool_output = tool._execute_tool(
                    record=record, **call.function.arguments
                )
                if isinstance(tool_output, dict):
                    tool_output = json.dumps(tool_output)
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": function_name,
                        "content": tool_output,
                    }
                )

    def _get_ollama_client_parameters(self):
        """
        We provide this hook so people can modify the client and other configurations
        like headers and so on.
        """
        return {"host": self.url, "headers": {}}
