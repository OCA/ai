# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from uuid import uuid4

from odoo import api, fields, models


class McpServer(models.Model):
    _name = "mcp.server"
    _description = "Mcp Server"

    name = fields.Char()
    description = fields.Text()
    active = fields.Boolean(default=True)
    key = fields.Char(
        required=True,
        copy=False,
        default=lambda self: uuid4(),
        groups="base.group_system",
    )
    tool_ids = fields.Many2many(
        "ai.tool", string="Tools", domain=[("kind", "=", "generic")]
    )
    url = fields.Char(
        compute="_compute_url",
        groups="base.group_system",
    )
    key_ids = fields.One2many("mcp.server.key", "server_id", string="Access Keys")

    _sql_constraints = [
        ("key_uniq", "unique(key)", "The key must be unique"),
    ]

    @api.depends("key")
    def _compute_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for record in self:
            record.url = f"{base_url}/mcp/{record.key}"
