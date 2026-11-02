# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from odoo.addons.ai_tool.tools import aitool


class AiSkill(models.Model):
    _name = "ai.skill"
    _description = "AI Skill"
    _inherits = {"ai.tool": "tool_id"}

    tool_id = fields.Many2one(
        "ai.tool", required=True, ondelete="cascade", auto_join=True
    )
    content = fields.Text(
        required=True,
        help="Detailed instructions and guidelines in Markdown format.",
    )

    model_id = fields.Many2one(
        default=lambda self: self.env["ir.model"]._get("ai.skill").id
    )
    function_name = fields.Char(default="_ai_get_skill_content")
    kind = fields.Selection(default="generic")

    @aitool(
        input_schema={},
        output_schema={
            "name": {"type": "string"},
            "content": {"type": "string"},
        },
    )
    def _ai_get_skill_content(self, **kwargs):
        return {
            "name": self.name,
            "content": self.content,
        }
