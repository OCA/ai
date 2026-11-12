# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, models


class AiLlmClient(models.AbstractModel):
    _inherit = "ai.llm.client"

    @api.model
    def _prepare_openai_tools(self, tools):
        """Convert an ai.tool recordset into OpenAI tool schemas when needed."""
        if isinstance(tools, models.BaseModel) and tools._name == "ai.tool":
            return tools.get_openai_tools_definitions()
        return tools

    @api.model
    def _prepare_chat_options(
        self,
        options: dict | None = None,
        tools=None,
        tool_choice=None,
        **kwargs,
    ) -> dict:
        prepared_tools = self._prepare_openai_tools(tools)
        return super()._prepare_chat_options(
            options=options,
            tools=prepared_tools,
            tool_choice=tool_choice,
            **kwargs,
        )

    @api.model
    def decide_tool(
        self,
        input_data,
        tools,
        instructions: str,
        include_done: bool = True,
        name: str = "next_action",
        model: str | None = None,
        options: dict | None = None,
    ) -> dict | None:
        """Select the next ai.tool (or 'done') via System 1 Decision Model."""
        choices = tools.get_decision_tool_candidates(include_done=include_done)
        return self.decide_choice(
            input_data=input_data,
            choices=choices,
            instructions=instructions,
            name=name,
            model=model,
            options=options,
        )
