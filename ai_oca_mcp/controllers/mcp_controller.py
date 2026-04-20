import json
import re

from odoo import fields, http
from odoo.http import request


class McpController(http.Controller):
    @http.route(
        "/mcp/<string:key>", type="http", auth="none", methods=["POST"], csrf=False
    )
    def mcp_endpoint(self, key, **kwargs):
        match = re.match(
            r"Bearer (.+)", request.httprequest.headers.get("Authorization", "")
        )
        payload = json.loads(request.httprequest.data.decode("utf-8"))
        if not match:
            return request.make_json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "error": {"code": -32000, "message": "Connection failed"},
                },
                status=401,
            )
        security_key = match.group(1).strip()
        server_id, expiration_date = (
            request.env["mcp.server.key"]
            .sudo()
            ._get_mcp_server_by_key(key, security_key)
        )
        if expiration_date and expiration_date < fields.Datetime.now():
            request.env["mcp.server.key"].sudo().browse(server_id).expire_key()
            server_id = False
        if not server_id:
            return request.make_json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "error": {"code": -32000, "message": "Connection failed"},
                }
            )
        server = request.env["mcp.server.key"].sudo().browse(server_id)
        server = server.with_user(server.user_id.id)
        method = payload.get("method")
        if method == "initialize":
            return request.make_json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "odoo-mcp", "version": "0.1.0"},
                    },
                }
            )

        if method == "tools/list":
            return request.make_json_response(server._tools_list(payload))

        if method == "tools/call":
            return request.make_json_response(server._tools_call(payload))

        return request.make_json_response(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32601, "message": "Method not found"},
            }
        )
