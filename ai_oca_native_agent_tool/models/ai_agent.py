# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
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

    def get_tools_definitions(self):
        """Return formatted tool declarations for LLM function calling schema."""
        self.ensure_one()
        tools_definitions = []
        for tool in self.tool_ids:
            definition = tool._get_tool_definition()
            tools_definitions.append(definition)
        return tools_definitions

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
        tool_sudo = tool.sudo()
        model_name = tool_sudo.model_id.model
        func_name = tool_sudo.function_name
        kind = tool_sudo.kind

        target_env = self.env[model_name].with_user(target_user)
        if kind == "generic":
            return getattr(target_env, func_name)(**params)
        if not record:
            raise ValueError("Record must be provided for non-generic tools")
        if kind == "generic_model":
            return getattr(target_env, func_name)(record=record, **params)
        elif record._name != model_name:
            raise ValueError(
                f"Record model {record._name} does not match tool model {model_name}"
            )
        return getattr(record.with_user(target_user), func_name)(**params) or {}

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
    def agent_propose_action_plan(self, summary, steps, **kwargs):
        plan_payload = ActionPlanPayload(summary=summary, steps=steps)
        return {
            "status": "awaiting_approval",
            "payload": plan_payload.model_dump(),
        }
