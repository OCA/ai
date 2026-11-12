# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import contextlib
import json

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.ai_oca_native_agent.models.schemas import ActionPlanPayload
from odoo.addons.ai_tool.tools import aitool


class AiAgent(models.Model):
    _inherit = "ai.agent"

    tool_ids = fields.Many2many(
        "ai.tool",
        "ai_agent_tool_rel",
        "agent_id",
        "tool_id",
        string="Allowed Tools",
    )

    def _prepare_tool_definition(self, tool) -> dict:
        """Hook to allow subclasses to customize or enrich a tool definition."""
        self.ensure_one()
        return tool._prepare_tool_definition()

    def get_openai_tools_definitions(self, tool_names=None):
        """Return formatted tool declarations for OpenAI tool calling schema."""
        self.ensure_one()
        tools = self.tool_ids
        if tool_names is not None:
            allowed_names = set(tool_names)
            tools = tools.filtered(lambda t: t.name in allowed_names)
        return [
            tool._to_openai_tool(definition=self._prepare_tool_definition(tool))
            for tool in tools
        ]

    def get_decision_tool_candidates(self, include_done: bool = True) -> list[dict]:
        """Return candidate choices formatted for System 1 Decision Model routing."""
        self.ensure_one()
        candidates = [
            tool._to_decision_choice(definition=self._prepare_tool_definition(tool))
            for tool in self.tool_ids
        ]
        if include_done:
            candidates.append(self.env["ai.tool"]._get_done_decision_choice())
        return candidates

    def tool_requires_arguments(self, tool_name: str) -> bool:
        """Return True if the named tool declares input arguments."""
        self.ensure_one()
        tool = self.tool_ids.filtered(lambda t: t.name == tool_name)[:1]
        if not tool:
            return False
        return tool._requires_arguments(definition=self._prepare_tool_definition(tool))

    def execute_tool(self, tool_name, params=None, record=None):
        """Execute named tool under agent's execution_mode security context."""
        self.ensure_one()
        params = params or {}
        tool = self.tool_ids.filtered(lambda t: t.name == tool_name)
        if not tool:
            raise UserError(
                self.env._(
                    "Tool '%(tool_name)s' is not allowed or configured "
                    "for Agent '%(agent_name)s'.",
                    tool_name=tool_name,
                    agent_name=self.name,
                )
            )
        target_user = (
            self.env.user
            if self.execution_mode == "user_context"
            else (self.user_id or self.env.user)
        )
        record = record.with_user(target_user) if record else None
        return (
            tool.with_user(target_user)
            .with_context(active_test=True)
            ._execute_tool(record=record, **params)
        )

    @aitool(
        input_schema={
            "res_model": {
                "type": "string",
                "description": "Optional model name filter (e.g. sale.order)",
            },
        },
        output_schema={
            "tools": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "model": {"type": "string"},
                    },
                },
            },
        },
    )
    def agent_list_available_tools(self, res_model=None, **kwargs):
        domain = []
        if res_model:
            domain.append(("model_id.model", "=", res_model))
        tools = self.env["ai.tool"].sudo().search(domain)
        result = []
        for t in tools:
            result.append(
                {
                    "name": t.name,
                    "description": t.description or "",
                    "model": t.model_id.model if t.model_id else "",
                }
            )
        return {"tools": result}

    @aitool(
        input_schema={
            "res_model": {
                "type": "string",
                "description": "Optional model name filter (e.g. crm.lead)",
            },
        },
        output_schema={
            "agents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "execution_mode": {"type": "string"},
                    },
                },
            },
        },
    )
    def agent_list_available_agents(self, res_model=None, **kwargs):
        domain = [("active", "=", True)]
        agents = self.env["ai.agent"].sudo().search(domain)
        result = []
        for a in agents:
            result.append(
                {
                    "name": a.name,
                    "description": a.description or "",
                    "execution_mode": a.execution_mode,
                }
            )
        return {"agents": result}

    @aitool(
        input_schema={
            "summary": {
                "type": "string",
                "description": "Global summary of proposed plan",
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "integer"},
                        "objective": {"type": "string"},
                        "target_type": {"type": "string"},
                        "target_name": {"type": "string"},
                        "params": {"type": "object"},
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["step_id", "objective", "target_type", "target_name"],
                },
            },
        },
        required_inputs=["summary", "steps"],
        output_schema={
            "status": {"type": "string"},
            "payload": {"type": "object"},
        },
    )
    def agent_propose_action_plan(self, summary=None, steps=None, **kwargs):
        if not summary or steps is None:
            raise ValueError(
                "Both 'summary' and 'steps' are required to propose an action plan."
            )
        if isinstance(steps, str):
            with contextlib.suppress(json.JSONDecodeError):
                steps = json.loads(steps)
        plan_payload = ActionPlanPayload(summary=summary, steps=steps)
        return {
            "status": "awaiting_approval",
            "payload": plan_payload.model_dump(),
        }
