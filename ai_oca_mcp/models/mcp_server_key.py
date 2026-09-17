# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from hashlib import sha256

from odoo import api, fields, models, tools


class McpServerKey(models.Model):
    _name = "mcp.server.key"
    _description = "Mcp Server Key"

    name = fields.Char(required=True)
    server_id = fields.Many2one("mcp.server", required=True, ondelete="cascade")
    hashed_key = fields.Char(copy=False)
    state = fields.Selection(
        [("active", "Active"), ("expired", "Expired")], default="active"
    )
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    expiration_date = fields.Datetime()
    expired_on = fields.Datetime(readonly=True)

    def expire_key(self):
        self.filtered(lambda key: key.state == "active").write(
            {
                "state": "expired",
                "expired_on": fields.Datetime.now(),
            }
        )
        self._get_mcp_server_by_key.clear_cache(self)

    _sql_constraints = [
        ("key_uniq", "unique(hashed_key)", "The key must be unique"),
    ]

    @api.model
    def _hash_key(self, key):
        return sha256(key.encode()).hexdigest()

    @tools.ormcache("key", "security_key")
    def _get_mcp_server_by_key(self, key, security_key):
        key = self.sudo().search(
            [
                ("server_id.key", "=", key),
                ("server_id.active", "=", True),
                ("hashed_key", "=", self._hash_key(security_key)),
                "|",
                ("expiration_date", "=", False),
                ("expiration_date", ">", fields.Datetime.now()),
                ("state", "=", "active"),
            ],
            limit=1,
        )
        return (key.id, key.expiration_date) if key else (False, False)

    def _tools_list(self, payload):
        tools = self.server_id.tool_ids
        result = []
        for tool in tools:
            result.append(tool._get_tool_definition())
        return {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"tools": result}}

    def _tools_call(self, payload):
        params = payload.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})
        result_vals = {
            "request": json.dumps(params),
            "server_id": self.server_id.id,
            "server_key_id": self.id,
        }

        tool = self.server_id.tool_ids.filtered(lambda t: t.name == tool_name)

        if not tool:
            self._add_log(**result_vals, error="Tool not found")
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32000, "message": "Unknown tool"},
            }
        try:
            with self.env.cr.savepoint(flush=False):
                result = tool._execute_tool(**args) or {}
                self._add_log(**result_vals, response=json.dumps(result))
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "structuredContent": result,
                    "content": [{"type": "text", "text": json.dumps(result)}],
                },
            }
        except Exception as e:
            self._add_log(**result_vals, error=str(e))
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32000, "message": str(e)},
            }

    def _add_log(self, **log_vals):
        return self.env["mcp.server.log"].sudo().create(log_vals)
