# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class McpServerLog(models.Model):
    _name = "mcp.server.log"
    _description = "Mcp Server Log"

    server_id = fields.Many2one("mcp.server", required=True, ondelete="cascade")
    server_key_id = fields.Many2one("mcp.server.key", required=True, ondelete="cascade")
    request = fields.Text()
    response = fields.Text()
    error = fields.Text()
    date = fields.Datetime(default=fields.Datetime.now, index=True)
