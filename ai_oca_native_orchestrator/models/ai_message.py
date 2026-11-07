# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AiMessage(models.Model):
    _inherit = "ai.message"

    status = fields.Selection(
        selection_add=[("awaiting_approval", "Awaiting Approval")],
        ondelete={"awaiting_approval": "cascade"},
    )
    payload = fields.Json(string="Structured Payload")

    def _process_assistant_message(self):
        self.ensure_one()
        if not self.exists() or self.status == "cancel":
            return

        task_thread = self._create_orchestrator_task_thread()
        ai_content = self._orchestrate_assistant_response(task_thread)
        if not ai_content:
            self.write(
                {"status": "cancel", "content": "Failed to get a response from LLM."}
            )
            self._notify_thread_bus_update(status="error")
            return

        vals = {"content": ai_content}
        if self.status != "awaiting_approval":
            vals["status"] = "done"
        self.write(vals)
        task_thread._add_message(ai_content, role="assistant")
        self._notify_thread_bus_update(status="success")

    def _create_orchestrator_task_thread(self):
        self.ensure_one()
        task_thread = (
            self.env["ai.task.thread"]
            .sudo()
            .create(
                {
                    "message_id": self.id,
                    "name": "Orchestrator Execution",
                }
            )
        )
        task_thread._add_message(
            self.content or "Processing user request",
            role="user",
        )
        return task_thread

    def _get_orchestrator_persona(self):
        self.ensure_one()
        if (
            self.thread_id
            and self.thread_id.agent_id
            and self.thread_id.agent_id.persona_id
        ):
            return self.thread_id.agent_id.persona_id
        return (
            self.env["ai.persona"].sudo().search([("is_default", "=", True)], limit=1)
        )

    def _get_orchestrator_system_prompt(self, persona=None):
        self.ensure_one()
        persona = persona or self._get_orchestrator_persona()
        if persona and persona.system_prompt_id:
            rendered = persona.system_prompt_id.render(thread=self.thread_id)
            if rendered:
                return [{"role": "system", "content": rendered}]
        return self.thread_id._get_system_prompt()

    def _get_orchestrator_llm_messages(self, persona=None):
        self.ensure_one()
        persona = persona or self._get_orchestrator_persona()
        system_messages = self._get_orchestrator_system_prompt(persona)

        thread_messages = self.thread_id.message_ids.filtered(
            lambda m: m.id != self.id and m.status != "cancel"
        ).sorted("create_date")

        if not thread_messages:
            return system_messages

        past_messages = thread_messages[:-1]
        latest_msg = thread_messages[-1]

        history_payload = []
        for msg in past_messages:
            history_payload.append(
                {
                    "role": msg.role,
                    "content": msg.content or "",
                }
            )

        user_content = latest_msg.content or ""
        if latest_msg.role == "user" and persona and persona.user_wrapper_prompt_id:
            rendered_user = persona.user_wrapper_prompt_id.render(
                content=user_content,
                thread=self.thread_id,
            )
            if rendered_user:
                user_content = rendered_user

        history_payload.append(
            {
                "role": latest_msg.role,
                "content": user_content,
            }
        )
        return system_messages + history_payload

    def _get_orchestrator_agent(self):
        self.ensure_one()
        if self.thread_id and self.thread_id.agent_id:
            return self.thread_id.agent_id
        return self.env.ref(
            "ai_oca_native_orchestrator.default_main_orchestrator_agent",
            raise_if_not_found=False,
        )

    def _parse_tool_call_args(self, tool_call):
        raw_args = tool_call.get("function", {}).get("arguments") or "{}"
        if isinstance(raw_args, dict):
            return raw_args
        try:
            return json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _execute_agent_tool(self, agent, tool_name, args):
        self.ensure_one()
        record = self.thread_id.record
        try:
            return agent.execute_tool(tool_name, params=args, record=record), None
        except Exception as err:
            return None, {"error": str(err)}

    def _handle_action_plan_proposal(
        self, task_thread, plan_payload, args, content=None
    ):
        self.ensure_one()
        self.write(
            {
                "payload": plan_payload,
                "status": "awaiting_approval",
            }
        )
        task_thread._add_message(
            content=f"Proposed action plan: {args.get('summary', '')}",
            role="assistant",
            payload=plan_payload,
        )
        steps_summary = "\n".join(
            f"- Step {s.get('step_id')}: {s.get('objective')}"
            for s in (plan_payload.get("steps") or [])
        )
        return (
            content
            if content
            else f"### Action Plan: {args.get('summary', '')}\n\n{steps_summary}\n\n*Awaiting approval to execute.*"
        )

    def _process_tool_call(self, agent, tool_call, task_thread, content=None):
        tool_name = tool_call["function"]["name"]
        call_id = tool_call["id"]
        args = self._parse_tool_call_args(tool_call)

        result, error = self._execute_agent_tool(agent, tool_name, args)

        if tool_name == "agent_propose_action_plan" and not error:
            early_text = self._handle_action_plan_proposal(
                task_thread=task_thread,
                plan_payload=result.get("payload"),
                args=args,
                content=content,
            )
            return None, early_text

        tool_result = error or result
        task_thread._add_message(
            content=f"Executed tool '{tool_name}' with args {json.dumps(args)}",
            role="assistant",
        )
        task_thread._add_message(
            content=json.dumps(tool_result),
            role="tool",
            payload=tool_result,
        )
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(tool_result),
        }, None

    def _orchestrate_assistant_response(self, task_thread, max_iterations=5):
        self.ensure_one()
        agent = self._get_orchestrator_agent()
        tools = agent.get_openai_tools_definitions() if agent else []
        llm_messages = self._get_orchestrator_llm_messages()

        if not tools:
            return self.chat(llm_messages, model_type="fast")

        current_messages = list(llm_messages)
        content = None
        for _iteration in range(max_iterations):
            response = self.chat(
                current_messages,
                tools=tools,
                tool_choice="required"
            )
            if not response:
                return None

            if isinstance(response, str):
                return response

            content = response.get("content")
            tool_calls = response.get("tool_calls") or []

            if not tool_calls:
                return content

            current_messages.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": tool_calls,
                }
            )

            for tool_call in tool_calls:
                tool_msg, early_text = self._process_tool_call(
                    agent, tool_call, task_thread, content=content
                )
                if early_text:
                    return early_text
                current_messages.append(tool_msg)

        return content or "Maximum reasoning iterations reached."

    def _notify_thread_bus_update(self, status="success"):
        self.ensure_one()
        user_partner = self.thread_id.user_id.partner_id
        payload = {
            "thread_id": self.thread_id.id,
            "thread_name": self.thread_id.name,
            "res_model": self.thread_id.res_model,
            "res_id": self.thread_id.res_id,
            "status": status,
            "message": self.thread_id.get_full_messages(self.thread_id.id)[-1],
        }
        self.env["bus.bus"]._sendone(user_partner, "ai_thread_update", payload)
