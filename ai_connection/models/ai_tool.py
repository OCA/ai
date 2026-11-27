# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import copy

from odoo import models

ACTIVITY_ARGUMENT = "activity"
ACTIVITY_DESCRIPTION = (
    "Short sentence, in the language of the user, in the present continuous "
    "and ending with '...', describing what you are doing with this call "
    "in business terms, e.g. 'Reading the quantity of the sale order...'."
)


class AiTool(models.Model):
    _inherit = "ai.tool"

    def _ai_tool_injects_activity(self):
        """Whether the ``activity`` argument is injected for this tool.

        Only when requested through the ``ai_tool_activity`` context and the
        tool does not already define an argument with that name.
        """
        self.ensure_one()
        if not self.env.context.get("ai_tool_activity"):
            return False
        func = getattr(self.env[self.model_id.model], self.function_name)
        properties = func._ai_tool["input_schema"].get("properties") or {}
        return ACTIVITY_ARGUMENT not in properties

    def _get_tool_definition(self):
        definition = super()._get_tool_definition()
        if not self._ai_tool_injects_activity():
            return definition
        # The schema comes from the decorated method, shared by every call:
        # never modify it in place.
        input_schema = copy.deepcopy(definition["inputSchema"])
        input_schema.setdefault("properties", {})[ACTIVITY_ARGUMENT] = {
            "type": "string",
            "description": ACTIVITY_DESCRIPTION,
        }
        input_schema["required"] = [
            *input_schema.get("required", []),
            ACTIVITY_ARGUMENT,
        ]
        return dict(definition, inputSchema=input_schema)
