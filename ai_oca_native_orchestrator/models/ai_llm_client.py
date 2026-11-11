# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, models


class AiLlmClient(models.AbstractModel):
    _inherit = "ai.llm.client"

    @api.model
    def _extract_called_tools(self, input_data) -> set[str]:
        """Return tool names already called in a message list input."""
        if not isinstance(input_data, (list, tuple)):
            return set()
        called = set()
        for item in input_data:
            if isinstance(item, dict):
                for tc in item.get("tool_calls") or []:
                    fn_name = (tc.get("function") or {}).get("name")
                    if fn_name:
                        called.add(fn_name)
        return called

    @api.model
    def _prepare_decision_choices(self, input_data, choices: list[dict]) -> list[dict]:
        prepared = super()._prepare_decision_choices(input_data, choices)
        called_tools = self._extract_called_tools(input_data)
        return [
            c
            for c in prepared
            if c.get("value") == "done" or c.get("value") not in called_tools
        ]
