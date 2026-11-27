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
        on_step=None,
        tool_activity=False,
        next_iteration=None,
        iteration=1,
    ):
        """Run the conversation against the AI system.

        :param on_step: optional callable receiving a dict for every step of
            the loop: ``llm_call`` (before asking the AI), ``iteration``
            (after each AI response), ``tool_call`` (before running a tool)
            and ``tool_result`` (after running it).
            This method never commits: the caller decides what to do.
        :param tool_activity: inject an ``activity`` argument in the tool
            definitions, asking the AI for a short description of what it is
            doing. It is removed before running the tool and reported in the
            ``tool_call``/``tool_result`` steps.
        :param next_iteration: see ``_ai_next_iteration``: optional callable
            to run each next iteration elsewhere (a cron, a job...) instead of
            right away. ``_run`` then returns ``None`` after the first
            iteration that calls tools.
        :param iteration: number of the first iteration, to go on with a
            conversation stopped by ``next_iteration`` (with its ``messages``).
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
        return self._run_ai(
            messages=messages,
            tools=tools,
            record=record,
            max_iterations=max_iterations,
            on_step=on_step,
            tool_activity=tool_activity,
            next_iteration=next_iteration,
            iteration=iteration,
        )

    def _run_ai(
        self,
        messages,
        tools=None,
        record=None,
        max_iterations=None,
        on_step=None,
        tool_activity=False,
        next_iteration=None,
        iteration=1,
    ):
        if tools and tool_activity:
            tools = tools.with_context(ai_tool_activity=True)
        return self._run_ai_iteration(
            {
                # Shallow copying messages to avoid edition of the messages
                "messages": list(messages),
                "iteration": iteration,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            },
            tools=tools,
            record=record,
            max_iterations=max_iterations or self._max_iterations,
            on_step=on_step,
            tool_activity=tool_activity,
            next_iteration=next_iteration,
        )

    def _run_ai_iteration(
        self,
        state,
        tools=None,
        record=None,
        max_iterations=None,
        on_step=None,
        tool_activity=False,
        next_iteration=None,
    ):
        """Ask the AI once, run the tools it calls and go on with the next.

        ``state`` holds everything needed to go on, JSON serializable:
        ``messages``, ``iteration`` (number of this one) and the token usage
        so far. Returns the final answer as ``(content, prompt_tokens,
        completion_tokens, iteration)``, or ``None`` when the next iteration
        runs elsewhere (see ``_ai_next_iteration``).
        """
        iteration = state["iteration"]
        max_iterations = max_iterations or self._max_iterations
        if iteration > max_iterations:
            raise UserError(
                self.env._(
                    "Iterations reached the maximum allowed (%s)", max_iterations
                )
            )
        client = getattr(self, f"_get_client_{self.kind}")(tools)
        messages = state["messages"]
        self._notify_step(on_step, {"type": "llm_call", "iteration": iteration})
        response = client.handle_message(
            messages=messages, temperature=self.temperature
        )
        messages.append(response["message"])
        usage = response.get("usage", {})
        state["prompt_tokens"] += usage.get("prompt_tokens", 0)
        state["completion_tokens"] += usage.get("completion_tokens", 0)
        self._notify_step(
            on_step,
            {
                "type": "iteration",
                "iteration": iteration,
                "content": response["message"].get("content"),
                "reasoning": response.get("reasoning"),
                "tool_calls": response.get("tool_calls") or [],
                "usage": usage,
            },
        )
        if not response.get("tool_calls"):
            return (
                response["message"]["content"],
                state["prompt_tokens"],
                state["completion_tokens"],
                iteration,
            )
        for tool_call in response["tool_calls"]:
            messages.append(
                self._run_tool_call(
                    tools, tool_call, record, on_step, iteration, tool_activity
                )
            )
        state["iteration"] = iteration + 1
        return self._ai_next_iteration(
            state,
            tools=tools,
            record=record,
            max_iterations=max_iterations,
            on_step=on_step,
            tool_activity=tool_activity,
            next_iteration=next_iteration,
        )

    def _ai_next_iteration(self, state, next_iteration=None, **kwargs):
        """Go on with the next iteration of the conversation.

        Right away by default. With ``next_iteration``, it gets the ``state``
        instead and the conversation stops here (``None`` is returned): the
        caller runs the next iteration when and where it wants, e.g. in
        another cron job or a queued job, calling ``_run`` again with
        ``messages=state["messages"]`` and ``iteration=state["iteration"]``.
        Override it to change how the iterations are chained.
        """
        if next_iteration:
            next_iteration(state)
            return None
        return self._run_ai_iteration(state, **kwargs)

    def _notify_step(self, on_step, step):
        if on_step:
            on_step(step)

    def _run_tool_call(
        self, tools, tool_call, record, on_step, iteration, tool_activity=False
    ):
        """Run a single tool call and return the message answering it.

        Errors (including unknown tools) are answered to the AI instead of
        raised, so it can recover on the next iteration.
        """
        name = tool_call["name"]
        tool = tools.filtered(lambda t: t.name == name)[:1] if tools else None
        arguments = dict(tool_call.get("arguments") or {})
        activity = None
        if tool and tool_activity and tool._ai_tool_injects_activity():
            activity = arguments.pop("activity", None)
        step = {
            "iteration": iteration,
            "tool": name,
            "call_id": tool_call.get("id"),
            "arguments": arguments,
            "activity": activity,
        }
        self._notify_step(on_step, dict(step, type="tool_call"))
        error = None
        if not tool:
            error = self.env._("Tool %s does not exist", name)
            tool = self.env["ai.tool"].new({"name": name})
            tool_response = {"error": error, "type": "ToolNotFound"}
        else:
            try:
                with self.env.cr.savepoint():
                    tool_response = tool._execute_tool(**arguments, record=record)
            except Exception as e:
                error = str(e)
                tool_response = {"error": error, "type": type(e).__name__}
        self._notify_step(
            on_step,
            dict(step, type="tool_result", result=tool_response, error=error),
        )
        return self._get_tool_call_result(tool, tool_response, tool_call)

    def _get_tool_call_result(self, tool, tool_response, tool_call):
        return getattr(
            self,
            f"_process_tool_call_result_{self.kind}",
            self._process_tool_call_result,
        )(tool, tool_response, tool_call)

    def _process_tool_call(self, tool, tool_call, record):
        tool_response = tool._execute_tool(**tool_call["arguments"], record=record)
        return self._get_tool_call_result(tool, tool_response, tool_call)

    def _process_tool_call_result(self, tool, tool_response, tool_call):
        return {
            "role": "tool",
            "name": tool.name,
            "tool_call_id": tool_call.get("id"),
            "content": json.dumps(tool_response),
        }
