# Copyright 2026 Dixmit
# Copyright 2026 SDi <amoya@sdi.es>
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
        store=False,
        stepwise=False,
        debug=False,
        stream=False,
        stream_batch_size=40,
    ):
        """
        Executes a conversation or prompt using the configured AI client.

        :param prompt: Initial text prompt from the user.
        :param tools: `ai.tool` recordset of allowed tools.
        :param record: Odoo record the AI is running against.
        :param system_prompt: System prompt for instructions.
        :param messages: List of message history dictionaries.
        :param max_iterations: Maximum allowed loops (tool calls).
        :param attachments: `ir.attachment` recordset to send to the AI.

        Execution mode parameters:
        :param store: (bool) If True, creates an `ai.connection.execution` record
                      to persist the state, messages, and results in the database.
                      If False, the execution runs in memory and returns a tuple.
        :param stepwise: (bool) Requires `store=True`. If True, pauses the execution
                         after every tool call (or step), allowing manual resumption.
        :param debug: (bool) Requires `store=True`. If True, creates `iteration`
                      records for every step, saving the exact JSON payloads sent.
        :param stream: (bool) Triggers the `_on_stream_batch` hook incrementally as
                       the LLM generates text. Used with `store=True` so the
                       execution record can emit bus notifications for the frontend.
        :param stream_batch_size: (int) Number of chunks to accumulate before firing
                                  the stream hook.

        :return: If `store=True`, returns the created `ai.connection.execution` record.
                 If `store=False`, returns a tuple:
                 (accumulated_content, prompt_tokens, comp_tokens, iter_count)
        """
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

        if store:
            call_vals = {
                "connection_id": self.id,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "messages_json": messages,
                "tool_ids": [(6, 0, tools.ids)] if tools else False,
                "res_model": record._name if record else False,
                "res_id": record.id if record else False,
                "max_iterations": max_iterations or self._max_iterations,
                "debug": debug,
                "stepwise": stepwise,
                "stream": stream,
                "stream_batch_size": stream_batch_size,
            }
            call = self.env["ai.connection.execution"].create(call_vals)
            call.action_start()
            return call

        return self._run_ai(
            messages=messages,
            tools=tools,
            record=record,
            max_iterations=max_iterations,
            stream=stream,
            stream_batch_size=stream_batch_size,
        )

    def _run_ai(  # noqa: C901
        self,
        messages,
        tools=None,
        record=None,
        max_iterations=None,
        stream=False,
        stream_batch_size=40,
        execution_record=None,
    ):
        # Shallow copying messages to avoid edition of the messages
        messages = list(messages)
        if max_iterations is None:
            max_iterations = self._max_iterations

        iteration = 0
        prompt_tokens = 0
        completion_tokens = 0

        while iteration < max_iterations:
            iteration += 1

            accumulated_content, tool_calls, usage = self._execute_ai_call(
                messages, tools, stream, stream_batch_size, execution_record
            )

            response_message = {"role": "assistant", "content": accumulated_content}
            if tool_calls:
                response_message["tool_calls"] = tool_calls

            messages.append(response_message)
            prompt_tokens += usage.get("prompt_tokens", 0)
            completion_tokens += usage.get("completion_tokens", 0)

            if not tool_calls:
                return (
                    accumulated_content,
                    prompt_tokens,
                    completion_tokens,
                    iteration,
                )

            new_messages, pending_approval = self._process_tool_calls(
                tool_calls, tools, record, execution_record=execution_record
            )
            messages.extend(new_messages)
            if pending_approval:
                break

        raise UserError(
            self.env._("Iterations reached the maximum allowed (%s)", max_iterations)
        )

    def _get_stream_method(self, client):
        if hasattr(client, "handle_message_stream"):
            return client.handle_message_stream

        def stream_method(msgs, temperature=None):
            res = client.handle_message(msgs, temperature=temperature)
            if res.get("message", {}).get("content"):
                yield {"type": "content", "content": res["message"]["content"]}
            if res.get("tool_calls"):
                yield {"type": "tool_calls", "tool_calls": res["tool_calls"]}
            if res.get("usage"):
                yield {"type": "usage", "usage": res["usage"]}

        return stream_method

    def _execute_ai_call(
        self,
        messages,
        tools=None,
        stream=False,
        stream_batch_size=40,
        execution_record=None,
    ):
        """
        Executes a single call to the AI model, processing streams if available.
        """
        client = getattr(self, f"_get_client_{self.kind}")(tools)
        stream_method = self._get_stream_method(client)

        accumulated_content = ""
        tool_calls = []
        usage = {}
        chunk_count = 0

        response_iterator = stream_method(messages, temperature=self.temperature)
        for chunk in response_iterator:
            chunk_type = chunk.get("type")
            if chunk_type == "content":
                content_chunk = chunk.get("content", "")
                accumulated_content += content_chunk
                chunk_count += 1
                if stream and chunk_count % stream_batch_size == 0:
                    self._on_stream_batch(
                        accumulated_content,
                        is_done=False,
                        execution_record=execution_record,
                    )
            elif chunk_type == "tool_calls":
                tool_calls.extend(chunk.get("tool_calls", []))
            elif chunk_type == "usage":
                usage.update(chunk.get("usage", {}))

        if stream and chunk_count > 0:
            self._on_stream_batch(
                accumulated_content, is_done=True, execution_record=execution_record
            )

        return accumulated_content, tool_calls, usage

    def _on_stream_batch(self, accumulated_text, is_done=False, execution_record=None):
        """Hook meant to be overwritten or delegated to the active execution."""
        if execution_record:
            execution_record._on_stream_batch(accumulated_text, is_done=is_done)

    def _process_tool_calls(self, tool_calls, tools, record, execution_record=None):
        """
        Executes a list of tool calls and returns their messages.
        If an execution record is provided, it checks for approval
        and extracts attachments.
        Returns: (new_messages, pending_approval)
        """
        new_messages = []
        pending_approval = False

        for tool_call in tool_calls:
            tool = tools.filtered(lambda t, tc=tool_call: t.name == tc["name"])
            if tool:
                if execution_record and not execution_record._should_execute_tool(
                    tool, tool_call
                ):
                    pending_approval = True
                    break

                tool_msg = self._process_tool_call(tool, tool_call, record)

                if execution_record:
                    tool_msg = execution_record._extract_attachments(tool_msg)

                new_messages.append(tool_msg)

        return new_messages, pending_approval

    def _process_tool_call(self, tool, tool_call, record):
        try:
            tool_response = tool._execute_tool(**tool_call["arguments"], record=record)
        except Exception as e:
            tool_response = {"error": str(e)}
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
