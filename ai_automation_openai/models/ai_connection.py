# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

import openai

from odoo import fields, models


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[("openai", "OpenAI")], ondelete={"openai": "cascade"}
    )
    openai_api_key = fields.Char(groups="base.group_system")
    temperature = fields.Float(default=0, groups="base.group_system")

    def _run_openai(
        self, prompt, tools=None, messages=None, record=None, system_prompt=None
    ):
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
        openai_client = openai.OpenAI(**self.sudo()._get_openai_client_parameters())
        if messages is None:
            messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        while True:
            response = openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.sudo().temperature,
                tools=tool_definition or None,
            )
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls
            if not tool_calls:
                return response_message.content
            messages.append(response_message)
            for call in tool_calls:
                tool = tools.filtered(lambda t, call=call: t.name == call.function.name)
                tool_output = tool._execute_tool(
                    record=record, **json.loads(call.function.arguments)
                )
                if isinstance(tool_output, dict):
                    tool_output = json.dumps(tool_output)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": tool_output,
                    }
                )

    def _get_openai_client_parameters(self):
        params = {}
        if self.url:
            params["base_url"] = self.url
        if self.openai_api_key:
            params["api_key"] = self.openai_api_key
        return params
