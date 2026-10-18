# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode, urlsplit

from odoo import _, http
from odoo.http import request
from odoo.tools.misc import hmac as odoo_hmac

# Distinct scopes, so that a signed client_id is never accepted as a code.
CODE_SCOPE = "ai_oca_mcp_oauth.code"
CLIENT_SCOPE = "ai_oca_mcp_oauth.client"
CODE_LIFETIME = 300  # seconds
CLIENT_NAME_MAX_LENGTH = 64
# Claude (web, Desktop, mobile) and Claude Code, always allowed. Claude Code
# listens on a random port, so the port of a loopback URI is ignored when matching.
DEFAULT_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback",
    "http://localhost/callback",
    "http://127.0.0.1/callback",
]
LOOPBACK_HOSTS = ("localhost", "127.0.0.1")
# The parameters of an authorization request that the consent form posts back.
AUTHORIZE_PARAMS = (
    "response_type",
    "client_id",
    "redirect_uri",
    "state",
    "code_challenge",
    "code_challenge_method",
)


def _b64url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(env, scope, data):
    payload = _b64url_encode(json.dumps(data).encode())
    return f"{payload}.{odoo_hmac(env(su=True), scope, payload)}"


def _unsign(env, scope, value):
    """Return the data signed into ``value`` by ``_sign``, or None."""
    payload, _sep, signature = (value or "").rpartition(".")
    if not payload:
        return None
    expected = odoo_hmac(env(su=True), scope, payload)
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        return None
    return json.loads(_b64url_decode(payload))


def _match_redirect_uri(uri, allowed_uri):
    if uri == allowed_uri:
        return True
    parsed = urlsplit(uri)
    allowed = urlsplit(allowed_uri)
    return (
        allowed.hostname in LOOPBACK_HOSTS
        and parsed.scheme == allowed.scheme
        and parsed.hostname == allowed.hostname
        and parsed.username is None
        and parsed.path == allowed.path
        and parsed.query == allowed.query
    )


def _check_pkce(code_challenge, code_verifier):
    if not code_verifier:
        return False
    expected = _b64url_encode(hashlib.sha256(code_verifier.encode()).digest())
    return hmac.compare_digest(expected.encode(), code_challenge.encode())


class McpOAuthController(http.Controller):
    """OAuth 2.1 authorization server of the MCP servers.

    Each server is its own issuer, at the server URL. What Claude needs is
    supported: the authorization code flow with PKCE, and dynamic client
    registration. The access token is a regular ``mcp.server.key``, the same
    kind of key the "Add Key" wizard creates, owned by the user who approved
    the access.
    """

    @http.route(
        "/.well-known/oauth-protected-resource/mcp/<string:key>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def oauth_protected_resource(self, key):
        server = self._get_oauth_server_or_404(key)
        # The server URL is both the protected resource and the issuer.
        return request.make_json_response(
            {
                "resource": server.url,
                "authorization_servers": [server.url],
                "bearer_methods_supported": ["header"],
                "resource_name": server.name,
            }
        )

    @http.route(
        "/.well-known/oauth-authorization-server/mcp/<string:key>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def oauth_authorization_server(self, key):
        server = self._get_oauth_server_or_404(key)
        return request.make_json_response(
            {
                "issuer": server.url,
                "authorization_endpoint": f"{server.url}/oauth/authorize",
                "token_endpoint": f"{server.url}/oauth/token",
                "registration_endpoint": f"{server.url}/oauth/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
                "authorization_response_iss_parameter_supported": True,
            }
        )

    @http.route(
        "/mcp/<string:key>/oauth/register",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def oauth_register(self, key, **kwargs):
        """Dynamic client registration (RFC 7591).

        Clients are not stored: the client_id is signed and carries the
        server, the client's name and its redirect URIs.
        """
        server = self._get_oauth_server_or_404(key)
        try:
            metadata = json.loads(request.httprequest.get_data() or b"{}")
        except ValueError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        redirect_uris = metadata.get("redirect_uris")
        if (
            not isinstance(redirect_uris, list)
            or not redirect_uris
            or not all(self._is_allowed_redirect_uri(uri) for uri in redirect_uris)
        ):
            return self._oauth_error("invalid_redirect_uri")
        client_name = metadata.get("client_name")
        if isinstance(client_name, str):
            client_name = client_name.strip()[:CLIENT_NAME_MAX_LENGTH] or None
        else:
            client_name = None
        client_id = _sign(
            request.env,
            CLIENT_SCOPE,
            {
                "server_id": server.id,
                "name": client_name,
                "redirect_uris": redirect_uris,
            },
        )
        return request.make_json_response(
            {
                "client_id": client_id,
                "client_id_issued_at": int(time.time()),
                "client_name": client_name,
                "redirect_uris": redirect_uris,
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
            status=201,
        )

    @http.route(
        "/mcp/<string:key>/oauth/authorize",
        type="http",
        auth="user",
        methods=["GET"],
        sitemap=False,
        # With website installed, the login layout needs a website route.
        website=True,
        multilang=False,
    )
    def oauth_authorize(self, key, **kwargs):
        server, params, client, error = self._prepare_authorize(key, kwargs)
        return self._render_authorize(server, params, client, error)

    @http.route(
        "/mcp/<string:key>/oauth/authorize",
        type="http",
        auth="user",
        methods=["POST"],
        sitemap=False,
        website=True,
        multilang=False,
    )
    def oauth_authorize_submit(self, key, approve=None, **kwargs):
        server, params, client, error = self._prepare_authorize(key, kwargs)
        if error:
            return self._render_authorize(server, params, client, error)
        if not approve:
            return self._redirect_to_client(server, params, error="access_denied")
        return self._redirect_to_client(
            server, params, code=self._make_code(server, params, client)
        )

    @http.route(
        "/mcp/<string:key>/oauth/token",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def oauth_token(self, key, **kwargs):
        server = self._get_oauth_server_or_404(key)
        if kwargs.get("grant_type") != "authorization_code":
            return self._oauth_error("unsupported_grant_type")
        code = kwargs.get("code")
        data = _unsign(request.env, CODE_SCOPE, code)
        if (
            not data
            or data["exp"] < time.time()
            or data["server_id"] != server.id
            or data["client_id"] != kwargs.get("client_id")
            or data["redirect_uri"] != kwargs.get("redirect_uri")
            or not _check_pkce(data["code_challenge"], kwargs.get("code_verifier"))
        ):
            return self._oauth_error("invalid_grant")
        user = request.env["res.users"].sudo().browse(data["uid"]).exists()
        if not server._is_oauth_user_allowed(user):
            return self._oauth_error("invalid_grant")
        token = server._oauth_issue_key(
            user,
            code,
            data["client_name"],
            urlsplit(data["redirect_uri"]).hostname,
        )
        if not token:
            return self._oauth_error("invalid_grant")
        return request.make_json_response(
            {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": server._get_oauth_token_lifetime_days() * 86400,
            },
            headers=[("Cache-Control", "no-store")],
        )

    def _get_oauth_server_or_404(self, key):
        server = request.env["mcp.server"]._get_oauth_server(key)
        if not server:
            raise request.not_found()
        return server

    def _is_allowed_redirect_uri(self, uri):
        # A redirect URI never has a fragment (RFC 6749 3.1.2).
        if not isinstance(uri, str) or urlsplit(uri).fragment:
            return False
        param = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_oca_mcp_oauth.redirect_uris")
        )
        allowed_uris = DEFAULT_REDIRECT_URIS + (param.split() if param else [])
        return any(_match_redirect_uri(uri, allowed) for allowed in allowed_uris)

    def _prepare_authorize(self, key, kwargs):
        """Return the server, the request parameters, the client and an error."""
        server = self._get_oauth_server_or_404(key)
        params = {name: kwargs[name] for name in AUTHORIZE_PARAMS if name in kwargs}
        client = _unsign(request.env, CLIENT_SCOPE, params.get("client_id"))
        if client and client["server_id"] != server.id:
            client = None
        return (
            server,
            params,
            client,
            self._check_authorize_request(server, params, client),
        )

    def _check_authorize_request(self, server, params, client):
        """Return an error message, or None when the request is valid."""
        redirect_uri = params.get("redirect_uri")
        if not self._is_allowed_redirect_uri(redirect_uri):
            return _("The application's redirect URI is not allowed.")
        if not client:
            return _(
                "The application is not registered with this server. Remove it "
                "from the AI client and add it again."
            )
        if not any(
            _match_redirect_uri(redirect_uri, uri) for uri in client["redirect_uris"]
        ):
            return _("The application did not register this redirect URI.")
        if params.get("response_type") != "code":
            return _("Unsupported response type.")
        if not params.get("code_challenge") or (
            params.get("code_challenge_method") != "S256"
        ):
            return _("The application must use PKCE with the S256 method.")
        if not server._is_oauth_user_allowed(request.env.user):
            return _(
                "You are not allowed to connect AI clients. Ask your administrator "
                "to add you to the group 'Connect AI Clients with OAuth'."
            )
        return None

    def _render_authorize(self, server, params, client, error):
        redirect_host = urlsplit(params.get("redirect_uri") or "").hostname
        response = request.render(
            "ai_oca_mcp_oauth.authorize",
            {
                "server": server,
                "params": params,
                "error": error,
                "client_name": client and client["name"],
                "redirect_host": redirect_host,
                "is_loopback": redirect_host in LOOPBACK_HOSTS,
            },
        )
        # The approval must not be clickjacked from another site.
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    def _make_code(self, server, params, client):
        return _sign(
            request.env,
            CODE_SCOPE,
            {
                "server_id": server.id,
                "uid": request.env.uid,
                "client_id": params["client_id"],
                "client_name": client["name"],
                "redirect_uri": params["redirect_uri"],
                "code_challenge": params["code_challenge"],
                "exp": int(time.time()) + CODE_LIFETIME,
            },
        )

    def _redirect_to_client(self, server, params, **values):
        # "iss" lets the client check which server answered (RFC 9207).
        values.update(state=params.get("state"), iss=server.url)
        query = urlencode({k: v for k, v in values.items() if v})
        redirect_uri = params["redirect_uri"]
        separator = "&" if urlsplit(redirect_uri).query else "?"
        return request.redirect(f"{redirect_uri}{separator}{query}", local=False)

    def _oauth_error(self, error):
        return request.make_json_response(
            {"error": error},
            headers=[("Cache-Control", "no-store")],
            status=400,
        )
