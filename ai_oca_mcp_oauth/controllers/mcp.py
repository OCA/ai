# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import fields, http
from odoo.http import request

from odoo.addons.ai_oca_mcp.controllers import mcp_controller


class McpController(mcp_controller.McpController):
    """The MCP endpoint as an OAuth protected resource (RFC 9728).

    The authorization server it points to is in ``oauth.py``.
    """

    @http.route()
    def mcp_endpoint(self, key, **kwargs):
        server = request.env["mcp.server"]._get_oauth_server(key)
        if server and not self._check_bearer(key):
            # Without a valid token, tell the client where to get one.
            return request.make_json_response(
                {"error": "invalid_token"},
                headers=[
                    (
                        "WWW-Authenticate",
                        'Bearer error="invalid_token", resource_metadata="%s"'
                        % server._get_oauth_metadata_url(),
                    )
                ],
                status=401,
            )
        return super().mcp_endpoint(key, **kwargs)

    @http.route(
        "/.well-known/oauth-protected-resource/mcp/<string:key>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def oauth_protected_resource(self, key):
        server = request.env["mcp.server"]._get_oauth_server(key)
        if not server:
            raise request.not_found()
        # The server URL is both the protected resource and the issuer.
        return request.make_json_response(
            {
                "resource": server.url,
                "authorization_servers": [server.url],
                "bearer_methods_supported": ["header"],
                "resource_name": server.name,
            }
        )

    def _check_bearer(self, key):
        """Check the bearer token as ai_oca_mcp does.

        ai_oca_mcp answers an invalid key with a 200, while an MCP client needs
        a 401 to start the OAuth flow. A key from OAuth also stops working when
        its user may no longer connect: archived, or out of the group.
        """
        match = re.match(
            r"Bearer (.+)", request.httprequest.headers.get("Authorization", "")
        )
        if not match:
            return False
        server_key_model = request.env["mcp.server.key"].sudo()
        server_key_id, expiration_date = server_key_model._get_mcp_server_by_key(
            key, match.group(1).strip()
        )
        server_key = server_key_model.browse(server_key_id)
        if expiration_date and expiration_date < fields.Datetime.now():
            server_key.expire_key()
            return False
        if (
            server_key.oauth_code_hash
            and not server_key.server_id._is_oauth_user_allowed(server_key.user_id)
        ):
            return False
        return bool(server_key)
