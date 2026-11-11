# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import copy
import json
import logging

from odoo import fields, models
from odoo.exceptions import UserError

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
            return (
                agent.with_context(ai_message_id=self.id).execute_tool(
                    tool_name, params=args, record=record
                ),
                None,
            )
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
            else (
                f"### Action Plan: {args.get('summary', '')}\n\n"
                f"{steps_summary}\n\n*Awaiting approval to execute.*"
            )
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

    def _decide_orchestrator_next_action(
        self, current_messages, candidates, task_thread
    ) -> str:
        self.ensure_one()
        decision = self.decide_choice(
            input_data=current_messages,
            choices=candidates,
            instructions=(
                "Select the best tool to advance the user request, "
                "or select 'done' if no further tool call is needed."
            ),
            name="next_action",
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
        return selected_action

    def _orchestrate_assistant_response(self, task_thread, max_iterations=5):
        self.ensure_one()
        agent = self._get_orchestrator_agent()
        llm_messages = self._get_orchestrator_llm_messages()

        if not agent or not agent.tool_ids:
            return self.chat(llm_messages, model_type="fast")

        candidates = agent.get_decision_tool_candidates(include_done=True)
        current_messages = list(llm_messages)
        content = None
        for iteration in range(max_iterations):
            selected_action = self._decide_orchestrator_next_action(
                current_messages, candidates, task_thread
            )
            if selected_action == "done":
                return self.chat(current_messages, model_type="fast")

            if not agent.tool_requires_arguments(selected_action):
                tool_call = {
                    "id": f"call_{selected_action}_{iteration}",
                    "type": "function",
                    "function": {
                        "name": selected_action,
                        "arguments": "{}",
                    },
                }
                current_messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [tool_call],
                    }
                )
                tool_msg, _early_text = self._process_tool_call(
                    agent, tool_call, task_thread
                )
                current_messages.append(tool_msg)
                continue

            selected_tools = agent.get_openai_tools_definitions(
                tool_names=[selected_action]
            )
            response = self.chat(
                current_messages,
                tools=selected_tools,
                tool_choice={
                    "type": "function",
                    "function": {"name": selected_action},
                },
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

    def action_execute_plan(self, plan_payload=None):
        """Initialize and dispatch asynchronous execution of an action plan DAG."""
        self.ensure_one()
        raw_payload = copy.deepcopy(plan_payload or self.payload or {})
        steps = raw_payload.get("steps") or []
        if not steps:
            raise UserError(self.env._("No action plan steps found to execute."))
        for step in steps:
            step["status"] = "pending"
            step["result"] = None
            step["task_thread_id"] = None
        raw_payload["plan_status"] = "running"
        self.write({"status": "processing", "payload": raw_payload})
        self._notify_thread_bus_update(status="processing")
        return self._dispatch_ready_plan_steps()

    def _dispatch_ready_plan_steps(self):
        """Enqueue ready pending plan steps, or complete plan when all are done."""
        self.ensure_one()
        payload = copy.deepcopy(self.payload or {})
        steps = payload.get("steps") or []
        done_step_ids = {s["step_id"] for s in steps if s.get("status") == "done"}
        ready_step_ids = []
        for step in steps:
            if step.get("status") != "pending":
                continue
            deps = step.get("depends_on") or []
            if all(dep_id in done_step_ids for dep_id in deps):
                step["status"] = "enqueued"
                ready_step_ids.append(step["step_id"])

        if (
            len(done_step_ids) == len(steps)
            and payload.get("plan_status") != "completed"
        ):
            payload["plan_status"] = "completed"
            self.write({"payload": payload})
            self.with_delay(
                channel=self.queue_job_channel_name,
            )._action_plan_completed()
            return []

        if ready_step_ids:
            self.write({"payload": payload})
            for step_id in ready_step_ids:
                self.with_delay(
                    channel=self.queue_job_channel_name,
                )._process_plan_step_job(step_id)
        return ready_step_ids

    def _process_plan_step_job(self, step_id, plan_id=None):
        """Execute a single DAG plan step asynchronously inside queue_job."""
        self.ensure_one()
        if not self.exists() or self.status == "cancel":
            return None

        payload = copy.deepcopy(self.payload or {})
        steps = payload.get("steps") or []
        step = next((s for s in steps if s.get("step_id") == step_id), None)
        if not step or step.get("status") == "done":
            return None

        done_steps = {
            s["step_id"]: s.get("result") for s in steps if s.get("status") == "done"
        }
        deps = step.get("depends_on") or []
        if any(dep_id not in done_steps for dep_id in deps):
            return None

        target_type = step.get("target_type")
        target_name = step.get("target_name")
        objective = step.get("objective") or f"Step {step_id}"
        step_params = copy.deepcopy(step.get("params") or {})

        # sudo() is used to create the audit ai.task.thread record for this step.
        task_thread = (
            self.env["ai.task.thread"]
            .sudo()
            .create(
                {
                    "message_id": self.id,
                    "name": f"Plan Step {step_id}: {target_name}",
                }
            )
        )

        if target_type == "agent":
            # sudo() is used to lookup the target sub-agent configuration;
            # execute_task enforces the sub-agent's execution_mode security context.
            sub_agent = (
                self.env["ai.agent"]
                .sudo()
                .search(
                    [("name", "=", target_name), ("active", "=", True)],
                    limit=1,
                )
            )
            if not sub_agent:
                raise UserError(
                    self.env._(
                        "Sub-agent '%(agent_name)s' was not found or is inactive.",
                        agent_name=target_name,
                    )
                )
            step_params.setdefault(
                "dependency_results",
                {str(dep_id): done_steps[dep_id] for dep_id in deps},
            )
            step_result = sub_agent.execute_task(
                task_thread=task_thread,
                goal=objective,
                params=step_params,
                record=self.thread_id.record,
            )
        else:
            agent = self._get_orchestrator_agent()
            task_thread._add_message(
                content=(
                    f"Objective: {objective}\n"
                    f"Executing tool '{target_name}' with params "
                    f"{json.dumps(step_params)}"
                ),
                role="user",
                payload=step_params or None,
            )
            step_result = agent.with_context(ai_message_id=self.id).execute_tool(
                target_name,
                params=step_params,
                record=self.thread_id.record,
            )
            task_thread.payload = step_result
            task_thread._add_message(
                content=json.dumps(step_result),
                role="tool",
                payload=step_result,
            )

        updated_payload = copy.deepcopy(self.payload or {})
        for s in updated_payload.get("steps", []):
            if s.get("step_id") == step_id:
                s["status"] = "done"
                s["result"] = step_result
                s["task_thread_id"] = task_thread.id
        self.write({"payload": updated_payload})
        self._dispatch_ready_plan_steps()
        return step_result

    def _action_plan_completed(self):
        """Synthesize final assistant response once all DAG plan steps finish."""
        self.ensure_one()
        if not self.exists() or self.status == "cancel":
            return

        payload = self.payload or {}
        steps = payload.get("steps") or []
        summary = payload.get("summary") or "Action Plan"
        steps_report = [
            {
                "step_id": s.get("step_id"),
                "objective": s.get("objective"),
                "target_type": s.get("target_type"),
                "target_name": s.get("target_name"),
                "result": s.get("result"),
            }
            for s in steps
        ]
        llm_messages = self._get_orchestrator_llm_messages()
        llm_messages.append(
            {
                "role": "user",
                "content": (
                    f"All steps of the action plan '{summary}' have been executed.\n"
                    f"Execution results:\n{json.dumps(steps_report)}\n"
                    "Provide a clear, concise final response summarizing the outcome."
                ),
            }
        )
        ai_content = self.chat(llm_messages, model_type="fast")
        if not ai_content:
            self.write(
                {
                    "status": "cancel",
                    "content": "Failed to synthesize action plan completion response.",
                }
            )
            self._notify_thread_bus_update(status="error")
            return

        self.write({"content": ai_content, "status": "done"})
        # sudo() is used to create the completion trace in ai.task.thread.
        synthesis_thread = (
            self.env["ai.task.thread"]
            .sudo()
            .create(
                {
                    "message_id": self.id,
                    "name": "Orchestrator Plan Synthesis",
                    "payload": {"steps_report": steps_report},
                }
            )
        )
        synthesis_thread._add_message(
            content=ai_content,
            role="assistant",
            payload={"steps_report": steps_report},
        )
        self._notify_thread_bus_update(status="success")

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
