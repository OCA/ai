# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import copy

from odoo import api, models


class AiTool(models.Model):
    _inherit = "ai.tool"

    def _prepare_tool_definition(self) -> dict:
        """Hook returning a mutable copy of the tool definition."""
        self.ensure_one()
        return copy.deepcopy(self._get_tool_definition())

    def _to_openai_tool(self, definition: dict | None = None) -> dict:
        """Convert a single ai.tool into an OpenAI function tool schema."""
        self.ensure_one()
        if definition is None:
            definition = self._prepare_tool_definition()
        return {
            "type": "function",
            "function": {
                "name": definition["name"],
                "description": definition.get("description") or "",
                "parameters": definition.get("inputSchema")
                or {"type": "object", "properties": {}},
            },
        }

    def get_openai_tools_definitions(self) -> list[dict]:
        """Convert all tools in recordset into OpenAI function tool schemas."""
        return [tool._to_openai_tool() for tool in self]

    @api.model
    def _get_done_decision_choice(self) -> dict:
        """Return standard 'done' candidate for System 1 Decision routing."""
        return {
            "value": "done",
            "description": (
                "Task is complete or can be answered directly "
                "without calling another tool."
            ),
        }

    def _to_decision_choice(self, definition: dict | None = None) -> dict:
        """Convert a single ai.tool into a System 1 Decision candidate choice."""
        self.ensure_one()
        if definition is None:
            definition = self._prepare_tool_definition()
        return {
            "value": self.name,
            "description": definition.get("description") or self.name,
        }

    def get_decision_tool_candidates(self, include_done: bool = True) -> list[dict]:
        """Convert all tools in recordset into System 1 Decision candidates."""
        candidates = [tool._to_decision_choice() for tool in self]
        if include_done:
            candidates.append(self._get_done_decision_choice())
        return candidates

    def _requires_arguments(self, definition: dict | None = None) -> bool:
        """Return True if the tool schema declares properties or required fields."""
        self.ensure_one()
        if definition is None:
            definition = self._prepare_tool_definition()
        input_schema = definition.get("inputSchema") or {}
        return bool(input_schema.get("properties") or input_schema.get("required"))
