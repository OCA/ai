# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


import json

from odoo import fields, models
from odoo.exceptions import UserError


class AiConnection(models.Model):
    _name = "ai.connection"
    _description = "AI Connection"
    _max_iterations = 50

    name = fields.Char(required=True)
    kind = fields.Selection([], required=True)
    active = fields.Boolean(default=True)
    url = fields.Char(groups="base.group_system")
    model = fields.Char(groups="base.group_system")
    temperature = fields.Float(default=0.8)

    def _run(
        self,
        prompt=None,
        tools=None,
        record=None,
        system_prompt=None,
        messages=None,
        max_iterations=None,
        attachments=None,
    ):
        if messages is None:
            messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if prompt or attachments:
            message = {"role": "user", "content": prompt or ""}
            if attachments:
                message["files"] = [
                    {
                        "name": attachment.name,
                        "content": attachment.datas.decode("utf-8"),
                        "mimetype": attachment.mimetype,
                    }
                    for attachment in attachments
                ]
            messages.append(message)
        return self._run_ai(
            messages=messages, tools=tools, record=record, max_iterations=max_iterations
        )

    def _run_ai(self, messages, tools=None, record=None, max_iterations=None):
        self.ensure_one()
        if max_iterations is None:
            max_iterations = self._max_iterations
        return self._run_ai_step(
            messages=list(messages),
            tools=tools,
            record=record,
            max_iterations=max_iterations,
            iteration=0,
            prompt_tokens=0,
            completion_tokens=0,
        )

    def _run_ai_step(
        self,
        messages,
        tools,
        record,
        max_iterations,
        iteration,
        prompt_tokens,
        completion_tokens,
    ):
        self.ensure_one()
        if iteration >= max_iterations:
            return self._run_ai_error(
                self.env._(
                    "Iterations reached the maximum allowed (%s)", max_iterations
                )
            )
        iteration += 1

        client = getattr(self, f"_get_client_{self.kind}")(tools)
        response = client.handle_message(
            messages=messages, temperature=self.temperature
        )
        messages = [*messages, response["message"]]
        prompt_tokens += response.get("usage", {}).get("prompt_tokens", 0)
        completion_tokens += response.get("usage", {}).get("completion_tokens", 0)

        if not response.get("tool_calls"):
            return self._run_ai_finalize(
                messages, prompt_tokens, completion_tokens, iteration
            )

        for tool_call in response["tool_calls"]:
            tool = tools.filtered(
                lambda t, tool_call=tool_call: t.name == tool_call["name"]
            )
            if tool:
                try:
                    with self.env.cr.savepoint():
                        messages.append(
                            self._process_tool_call(tool, tool_call, record)
                        )
                except Exception as e:
                    getattr(
                        self,
                        f"_process_tool_call_result_{self.kind}",
                        self._process_tool_call_result,
                    )(
                        tool,
                        {
                            "error": str(e),
                            "type": type(e).__name__,
                        },
                        tool_call,
                    )

        return self._run_ai_next(
            messages=messages,
            tools=tools,
            record=record,
            max_iterations=max_iterations,
            iteration=iteration,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _run_ai_next(
        self,
        messages,
        tools,
        record,
        max_iterations,
        iteration,
        prompt_tokens,
        completion_tokens,
    ):
        return self._run_ai_step(
            messages=messages,
            tools=tools,
            record=record,
            max_iterations=max_iterations,
            iteration=iteration,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _run_ai_finalize(self, messages, prompt_tokens, completion_tokens, iteration):
        return (messages[-1]["content"], prompt_tokens, completion_tokens, iteration)

    def _run_ai_error(self, message):
        raise UserError(message)

    def _process_tool_call(self, tool, tool_call, record):
        tool_response = tool._execute_tool(**tool_call["arguments"], record=record)
        return getattr(
            self,
            f"_process_tool_call_result_{self.kind}",
            self._process_tool_call_result,
        )(tool, tool_response, tool_call)

    def _process_tool_call_result(self, tool, tool_response, tool_call):
        return {
            "role": "tool",
            "name": tool.name,
            "tool_call_id": tool_call.get("id"),
            "content": json.dumps(tool_response),
        }
