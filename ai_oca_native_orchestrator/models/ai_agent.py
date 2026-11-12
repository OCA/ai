# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.ai_tool.tools import aitool


class AiAgent(models.Model):
    _inherit = "ai.agent"

    def _prepare_tool_definition(self, tool) -> dict:
        definition = super()._prepare_tool_definition(tool)
        if tool.name == "agent_delegate_task":
            # sudo() is used to read active sub-agent metadata for routing discovery.
            sub_agents = (
                self.env["ai.agent"]
                .sudo()
                .search([("active", "=", True), ("id", "!=", self.id)])
            )
            if sub_agents:
                agent_summaries = []
                for sub in sub_agents:
                    tools_desc = ", ".join(
                        f"{t.name} ({t.description or t.name})" for t in sub.tool_ids
                    )
                    sub_info = f"{sub.name}: {sub.description or sub.name}"
                    if tools_desc:
                        sub_info += f" [Tools: {tools_desc}]"
                    agent_summaries.append(sub_info)
                base_desc = definition.get("description") or ""
                definition["description"] = (
                    f"{base_desc} Available sub-agents: {'; '.join(agent_summaries)}."
                )
                definition["inputSchema"]["properties"]["agent_name"]["enum"] = [
                    sub.name for sub in sub_agents
                ]
        return definition

    def _get_subagent_system_prompt(self, task_thread=None):
        self.ensure_one()
        thread = (
            task_thread.message_id.thread_id
            if task_thread and task_thread.message_id
            else None
        )
        if self.persona_id and self.persona_id.system_prompt_id:
            rendered = self.persona_id.system_prompt_id.render(thread=thread)
            if rendered:
                return [{"role": "system", "content": rendered}]
        default_prompt = (
            self.description or f"You are {self.name}, a specialized Odoo AI sub-agent."
        )
        return [{"role": "system", "content": default_prompt}]

    def _build_subagent_user_content(self, goal, params=None, record=None) -> str:
        parts = []
        if record:
            parts.append(
                f"Context Record: {record._name} "
                f"(ID: {record.id}, Name: {record.display_name})"
            )
        if params or record:
            parts.append(f"Objective: {goal}")
        else:
            parts.append(goal)
        if params:
            parts.append(f"Parameters: {json.dumps(params)}")
        return "\n".join(parts)

    def execute_task(
        self, task_thread, goal, params=None, record=None, max_iterations=5
    ):
        """Execute a delegated task in task_thread using System 1 + System 2."""
        self.ensure_one()
        params = params or {}
        llm_client = self.env["ai.llm.client"]
        system_messages = self._get_subagent_system_prompt(task_thread=task_thread)
        user_content = self._build_subagent_user_content(
            goal, params=params, record=record
        )
        task_thread._add_message(user_content, role="user", payload=params or None)
        current_messages = system_messages + [{"role": "user", "content": user_content}]
        tool_outputs = []

        if self.tool_ids:
            candidates = self.get_decision_tool_candidates(include_done=True)
            for iteration in range(max_iterations):
                decision = llm_client.decide_choice(
                    input_data=current_messages,
                    choices=candidates,
                    instructions=(
                        f"You are sub-agent '{self.name}'. Select the best tool "
                        "to accomplish the objective, or 'done' when ready to answer."
                    ),
                    name="subagent_next_action",
                )
                selected_action = (
                    decision.get("choice")
                    if isinstance(decision, dict) and decision.get("choice")
                    else "done"
                )
                task_thread._add_message(
                    content=f"System 1 Decision: selected '{selected_action}'",
                    role="assistant",
                    payload=decision or {"choice": "done"},
                )
                if selected_action == "done":
                    break

                if not self.tool_requires_arguments(selected_action):
                    tool_args = {}
                    call_id = f"subcall_{selected_action}_{iteration}"
                else:
                    selected_tools = self.get_openai_tools_definitions(
                        tool_names=[selected_action]
                    )
                    response = llm_client.chat(
                        current_messages,
                        tools=selected_tools,
                        tool_choice={
                            "type": "function",
                            "function": {"name": selected_action},
                        },
                    )
                    if not isinstance(response, dict) or not response.get("tool_calls"):
                        break
                    first_call = response["tool_calls"][0]
                    call_id = (
                        first_call.get("id") or f"subcall_{selected_action}_{iteration}"
                    )
                    raw_args = first_call.get("function", {}).get("arguments") or "{}"
                    tool_args = (
                        raw_args if isinstance(raw_args, dict) else json.loads(raw_args)
                    )

                try:
                    tool_result = self.execute_tool(
                        selected_action, params=tool_args, record=record
                    )
                except Exception as err:
                    tool_result = {"error": str(err)}

                tool_outputs.append(
                    {
                        "tool": selected_action,
                        "params": tool_args,
                        "result": tool_result,
                    }
                )
                tool_call_entry = {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": selected_action,
                        "arguments": json.dumps(tool_args),
                    },
                }
                current_messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [tool_call_entry],
                    }
                )
                current_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(tool_result),
                    }
                )
                task_thread._add_message(
                    content=(
                        f"Executed tool '{selected_action}' "
                        f"with args {json.dumps(tool_args)}"
                    ),
                    role="assistant",
                )
                task_thread._add_message(
                    content=json.dumps(tool_result),
                    role="tool",
                    payload=tool_result,
                )

        final_answer = llm_client.chat(current_messages, model_type="fast") or ""
        result_payload = {
            "agent": self.name,
            "task_thread_id": task_thread.id,
            "status": "done",
            "result": final_answer,
            "tool_outputs": tool_outputs,
        }
        task_thread.payload = result_payload
        task_thread._add_message(
            content=final_answer or f"Completed task for {self.name}",
            role="assistant",
            payload=result_payload,
        )
        return result_payload

    @aitool(
        input_schema={
            "agent_name": {
                "type": "string",
                "description": (
                    "Name of the active sub-agent (ai.agent) to delegate the task to"
                ),
            },
            "objective": {
                "type": "string",
                "description": "Clear goal or instructions for the sub-agent",
            },
            "params": {
                "type": "object",
                "description": "Optional structured parameters for the sub-agent",
            },
        },
        required_inputs=["agent_name", "objective"],
        output_schema={
            "agent": {"type": "string"},
            "task_thread_id": {"type": "integer"},
            "status": {"type": "string"},
            "result": {"type": "string"},
            "tool_outputs": {"type": "array"},
        },
    )
    def agent_delegate_task(
        self,
        agent_name=None,
        objective=None,
        params=None,
        message_id=None,
        record=None,
        **kwargs,
    ):
        if not agent_name or not objective:
            raise ValueError(
                "Both 'agent_name' and 'objective' are required to delegate a task."
            )
        # sudo() is used to lookup active sub-agent configuration across Odoo;
        # tool execution inside execute_task respects sub-agent execution_mode.
        sub_agent = (
            self.env["ai.agent"]
            .sudo()
            .search(
                [("name", "=ilike", agent_name.strip()), ("active", "=", True)],
                limit=1,
            )
        )
        if not sub_agent:
            raise UserError(
                self.env._(
                    "Sub-agent '%(agent_name)s' was not found or is inactive.",
                    agent_name=agent_name,
                )
            )
        msg_id = message_id or self.env.context.get("ai_message_id")
        if not msg_id:
            raise ValueError(
                "An active ai.message (message_id or context ai_message_id) "
                "is required to delegate a task."
            )
        message = self.env["ai.message"].browse(msg_id)
        target_record = record if record is not None else message.thread_id.record
        # sudo() is used to create the audit ai.task.thread linked to the message.
        task_thread = (
            self.env["ai.task.thread"]
            .sudo()
            .create(
                {
                    "message_id": message.id,
                    "name": f"Sub-Agent: {sub_agent.name}",
                }
            )
        )
        return sub_agent.execute_task(
            task_thread=task_thread,
            goal=objective,
            params=params,
            record=target_record,
        )
