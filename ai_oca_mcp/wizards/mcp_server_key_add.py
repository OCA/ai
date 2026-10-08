# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import secrets

from odoo import fields, models


class McpServerKeyAdd(models.TransientModel):
    _name = "mcp.server.key.add"
    _description = "Wizard used to add a new key to an MCP Server"
    _inherits = {
        "mcp.server.key": "key_id",
    }
    key_id = fields.Many2one("mcp.server.key", ondelete="cascade", required=True)
    server_id = fields.Many2one("mcp.server", required=True, ondelete="cascade")
    key = fields.Char(readonly=True, string="Key to use")

    def generate_key(self):
        self.ensure_one()
        self.key = secrets.token_urlsafe(32)
        self.key_id.hashed_key = self.key_id._hash_key(self.key)
        action = self.get_formview_action()
        action["target"] = "new"
        return action

    def expire_key(self):
        # Dummy function necessary to use the same form view as mcp.server.key
        return {}
