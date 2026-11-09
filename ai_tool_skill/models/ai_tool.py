# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiTool(models.Model):
    _inherit = "ai.tool"

    skill_id = fields.Many2one(
        "ai.skill",
        compute="_compute_skill_id",
        string="Linked Skill",
    )

    def _compute_skill_id(self):
        skills = self.env["ai.skill"].search([("tool_id", "in", self.ids)])
        skill_map = {s.tool_id.id: s for s in skills}
        for tool in self:
            tool.skill_id = skill_map.get(tool.id, False)

    def _execute_tool(self, *args, record=None, **kwargs):
        if self.skill_id:
            return {
                "name": self.skill_id.name,
                "content": self.skill_id.content,
            }
        return super()._execute_tool(*args, record=record, **kwargs)
