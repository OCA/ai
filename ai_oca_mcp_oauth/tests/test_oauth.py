# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import hashlib
import json
import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.ai_oca_mcp_oauth.controllers import oauth
from odoo.addons.ai_oca_mcp_oauth.hooks import uninstall_hook

REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"
CODE_VERIFIER = "test-code-verifier-0123456789-0123456789-0123456789"


@tagged("post_install", "-at_install")
class TestMcpOAuth(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Odoo 16 may keep a routing map built by the at_install tests of a
        # module loaded before this one, without the routes of this module.
        cls.env["ir.http"]._clear_routing_map()
        cls.server = cls.env["mcp.server"].create(
            {
                "name": "Test Server",
                "tool_ids": [Command.link(cls.env.ref("ai_tool.current_date").id)],
                "oauth_enabled": True,
            }
        )
        cls.user = new_test_user(
            cls.env,
            login="mcp_oauth_user",
            groups="base.group_user,ai_oca_mcp_oauth.group_mcp_oauth",
        )
        cls.user_no_group = new_test_user(cls.env, login="mcp_oauth_no_group")
        new_test_user(
            cls.env,
            login="mcp_oauth_portal",
            groups="base.group_portal,ai_oca_mcp_oauth.group_mcp_oauth",
        )
        cls.code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(CODE_VERIFIER.encode()).digest())
            .rstrip(b"=")
            .decode()
        )

    def _mcp_initialize(self, server, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.url_open(
            f"/mcp/{server.key}",
            data=json.dumps({"jsonrpc": "2.0", "id": "1", "method": "initialize"}),
            headers=headers,
        )

    def _authorize_params(self, **overrides):
        params = {
            "response_type": "code",
            "client_id": "test-client",
            "redirect_uri": REDIRECT_URI,
            "state": "test-state",
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
        }
        params.update(overrides)
        return params

    def _authorize(self, approve=True, login="mcp_oauth_user", **overrides):
        """Open the consent page as ``login`` and submit it, return the response."""
        self.authenticate(login, login)
        params = self._authorize_params(**overrides)
        path = f"/mcp/{self.server.key}/oauth/authorize"
        page = self.url_open(f"{path}?{urlencode(params)}")
        self.assertEqual(page.status_code, 200)
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        self.assertTrue(csrf_token, "The consent page has no form")
        data = dict(params, csrf_token=csrf_token.group(1))
        if approve:
            data["approve"] = "1"
        return self.url_open(path, data=data, allow_redirects=False)

    def _get_code(self):
        response = self._authorize()
        self.assertEqual(response.status_code, 303)
        location = urlsplit(response.headers["Location"])
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}", REDIRECT_URI
        )
        query = parse_qs(location.query)
        self.assertEqual(query["state"], ["test-state"])
        self.assertEqual(query["iss"], [self.server.url])
        return query["code"][0]

    def _token(self, auth_code, **overrides):
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "test-client",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        }
        data.update(overrides)
        return self.url_open(f"/mcp/{self.server.key}/oauth/token", data=data)

    def test_unauthorized_points_to_metadata(self):
        for token in (None, "wrong"):
            response = self._mcp_initialize(self.server, token)
            self.assertEqual(response.status_code, 401)
            self.assertIn(
                "resource_metadata=",
                response.headers["WWW-Authenticate"],
            )
            self.assertIn(
                f"/.well-known/oauth-protected-resource/mcp/{self.server.key}",
                response.headers["WWW-Authenticate"],
            )

    def test_expired_key_is_unauthorized(self):
        self.env["mcp.server.key"].create(
            {
                "name": "Expired",
                "server_id": self.server.id,
                "hashed_key": self.env["mcp.server.key"]._hash_key("expired-key"),
                "expiration_date": fields.Datetime.now() - timedelta(days=1),
            }
        )
        response = self._mcp_initialize(self.server, "expired-key")
        self.assertEqual(response.status_code, 401)

    @mute_logger("odoo.http")
    def test_server_without_oauth(self):
        server = self.env["mcp.server"].create({"name": "No OAuth"})
        # The original behaviour of ai_oca_mcp is kept.
        response = self._mcp_initialize(server, "wrong")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WWW-Authenticate", response.headers)
        response = self.url_open(
            f"/.well-known/oauth-protected-resource/mcp/{server.key}"
        )
        self.assertEqual(response.status_code, 404)

    def test_metadata(self):
        resource = self.url_open(
            f"/.well-known/oauth-protected-resource/mcp/{self.server.key}"
        ).json()
        self.assertEqual(resource["resource"], self.server.url)
        self.assertEqual(resource["authorization_servers"], [self.server.url])
        authorization_server = self.url_open(
            f"/.well-known/oauth-authorization-server/mcp/{self.server.key}"
        ).json()
        self.assertEqual(authorization_server["issuer"], self.server.url)
        self.assertEqual(
            authorization_server["token_endpoint"], f"{self.server.url}/oauth/token"
        )
        self.assertEqual(
            authorization_server["code_challenge_methods_supported"], ["S256"]
        )
        self.assertTrue(
            authorization_server["authorization_response_iss_parameter_supported"]
        )

    def test_register(self):
        path = f"/mcp/{self.server.key}/oauth/register"
        for redirect_uri in (REDIRECT_URI, "http://localhost:4567/callback"):
            response = self.url_open(
                path,
                data=json.dumps({"redirect_uris": [redirect_uri]}),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 201)
            self.assertTrue(response.json()["client_id"])
        for redirect_uri in (
            "https://evil.example.com/callback",
            "http://localhost:4567/other",
            "http://localhost:4567@evil.example.com/callback",
            "http://localhost:4567/callback#fragment",
            f"{REDIRECT_URI}#fragment",
        ):
            response = self.url_open(
                path,
                data=json.dumps({"redirect_uris": [redirect_uri]}),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 400, redirect_uri)
            self.assertEqual(response.json()["error"], "invalid_redirect_uri")

    def test_redirect_uri_from_param(self):
        self.env["ir.config_parameter"].set_param(
            "ai_oca_mcp_oauth.redirect_uris",
            "https://client.example.com/callback\nhttps://other.example.com/cb",
        )
        for redirect_uri, status in (
            ("https://client.example.com/callback", 201),
            ("https://other.example.com/cb", 201),
            (REDIRECT_URI, 400),
        ):
            response = self.url_open(
                f"/mcp/{self.server.key}/oauth/register",
                data=json.dumps({"redirect_uris": [redirect_uri]}),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, status, redirect_uri)

    def test_authorize_requires_login(self):
        response = self.url_open(
            f"/mcp/{self.server.key}/oauth/authorize?"
            + urlencode(self._authorize_params()),
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertIn("/web/login?redirect=", response.headers["Location"])

    def test_full_flow(self):
        response = self._token(self._get_code())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        token = response.json()["access_token"]
        self.env.invalidate_all()
        server_key = self.server.key_ids.filtered(lambda k: k.user_id == self.user)
        self.assertEqual(len(server_key), 1)
        self.assertEqual(server_key.name, "OAuth (claude.ai)")
        self.assertTrue(server_key.expiration_date)
        # The token works on the MCP endpoint.
        response = self.url_open(
            f"/mcp/{self.server.key}",
            data=json.dumps({"jsonrpc": "2.0", "id": "1", "method": "tools/list"}),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["result"]["tools"][0]["name"],
            self.env.ref("ai_tool.current_date").name,
        )

    def test_code_used_twice(self):
        code = self._get_code()
        self.assertEqual(self._token(code).status_code, 200)
        response = self._token(code)
        self.assertEqual(response.json()["error"], "invalid_grant")
        # The code may have been stolen: the key it gave is expired.
        self.env.invalidate_all()
        self.assertEqual(self.server.key_ids.mapped("state"), ["expired"])

    def test_code_redeemed_concurrently(self):
        # The other request has created its key but not committed it yet, so
        # the search does not see it: the unique constraint stops this one.
        self.env["mcp.server.key"].create(
            {
                "name": "Other request",
                "server_id": self.server.id,
                "hashed_key": self.env["mcp.server.key"]._hash_key("other-token"),
                "oauth_code_hash": self.env["mcp.server.key"]._hash_key("code"),
            }
        )
        server_key_model = self.registry["mcp.server.key"]
        with patch.object(
            server_key_model, "search", return_value=self.env["mcp.server.key"]
        ):
            token = self.server._oauth_issue_key(self.user, "code", "claude.ai")
        self.assertIsNone(token)
        self.assertEqual(len(self.server.key_ids), 1)

    def _get_token(self):
        response = self._token(self._get_code())
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def test_manual_key_on_oauth_server(self):
        # A key added by hand is not bound to the OAuth group.
        self.env["mcp.server.key"].create(
            {
                "name": "Manual",
                "server_id": self.server.id,
                "user_id": self.user_no_group.id,
                "hashed_key": self.env["mcp.server.key"]._hash_key("manual-key"),
            }
        )
        response = self._mcp_initialize(self.server, "manual-key")
        self.assertEqual(response.status_code, 200)
        self.assertIn("result", response.json())

    def test_key_expires_while_cached(self):
        token = self._get_token()
        self.assertEqual(self._mcp_initialize(self.server, token).status_code, 200)
        with freeze_time(fields.Datetime.now() + timedelta(days=31)):
            response = self._mcp_initialize(self.server, token)
        self.assertEqual(response.status_code, 401)
        self.env.invalidate_all()
        self.assertEqual(self.server.key_ids.state, "expired")

    def test_user_disconnects_own_key(self):
        self._get_token()
        server_key = self.server.key_ids
        # The key shows in the user's preferences.
        self.assertEqual(
            self.user.with_user(self.user).read(["mcp_oauth_key_ids"])[0][
                "mcp_oauth_key_ids"
            ],
            server_key.ids,
        )
        with self.assertRaises(AccessError):
            server_key.with_user(self.user_no_group).action_disconnect()
        self.assertEqual(server_key.state, "active")
        server_key.with_user(self.user).action_disconnect()
        self.assertEqual(server_key.state, "expired")
        self.assertFalse(self.user.mcp_oauth_key_ids)

    def test_key_past_expiration_not_listed(self):
        self._get_token()
        # No client has used the key since it expired, so it is still active.
        self.server.key_ids.expiration_date = fields.Datetime.now() - timedelta(days=1)
        self.assertEqual(self.server.key_ids.state, "active")
        self.assertFalse(self.user.mcp_oauth_key_ids)

    def test_key_of_archived_user(self):
        token = self._get_token()
        self.user.active = False
        self.assertEqual(self._mcp_initialize(self.server, token).status_code, 401)

    def test_key_of_user_removed_from_group(self):
        token = self._get_token()
        self.user.groups_id -= self.env.ref("ai_oca_mcp_oauth.group_mcp_oauth")
        self.assertEqual(self._mcp_initialize(self.server, token).status_code, 401)

    def test_disable_oauth_expires_oauth_keys(self):
        self._get_token()
        manual_key = self.env["mcp.server.key"].create(
            {
                "name": "Manual",
                "server_id": self.server.id,
                "user_id": self.user.id,
                "hashed_key": self.env["mcp.server.key"]._hash_key("manual-key"),
            }
        )
        self.server.oauth_enabled = False
        oauth_key = self.server.key_ids - manual_key
        self.assertEqual(oauth_key.state, "expired")
        self.assertEqual(manual_key.state, "active")

    def test_uninstall_expires_oauth_keys(self):
        self._get_token()
        uninstall_hook(self.env.cr, self.registry)
        self.assertEqual(self.server.key_ids.state, "expired")

    def test_deny(self):
        response = self._authorize(approve=False)
        self.assertEqual(response.status_code, 303)
        query = parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertEqual(query["error"], ["access_denied"])
        self.assertEqual(query["state"], ["test-state"])
        self.assertEqual(query["iss"], [self.server.url])
        self.assertNotIn("code", query)

    def test_invalid_grant(self):
        code = self._get_code()
        for overrides in (
            {"code_verifier": "wrong-verifier"},
            {"redirect_uri": "http://localhost/callback"},
            {"client_id": "other-client"},
            {"code": code[:-1]},
        ):
            response = self._token(code, **overrides)
            self.assertEqual(response.status_code, 400, overrides)
            self.assertEqual(response.json()["error"], "invalid_grant")
        response = self._token(code, grant_type="refresh_token")
        self.assertEqual(response.json()["error"], "unsupported_grant_type")
        self.env.invalidate_all()
        self.assertFalse(self.server.key_ids)

    def test_expired_code(self):
        with patch.object(oauth, "CODE_LIFETIME", -1):
            code = self._get_code()
        response = self._token(code)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_code_bound_to_server(self):
        other_server = self.env["mcp.server"].create(
            {"name": "Other Server", "oauth_enabled": True}
        )
        response = self.url_open(
            f"/mcp/{other_server.key}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": self._get_code(),
                "client_id": "test-client",
                "redirect_uri": REDIRECT_URI,
                "code_verifier": CODE_VERIFIER,
            },
        )
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_consent_errors(self):
        self.authenticate("mcp_oauth_user", "mcp_oauth_user")
        path = f"/mcp/{self.server.key}/oauth/authorize"
        for overrides in (
            {"redirect_uri": "https://evil.example.com/callback"},
            {"code_challenge_method": "plain"},
            {"code_challenge": ""},
            {"response_type": "token"},
        ):
            response = self.url_open(
                f"{path}?{urlencode(self._authorize_params(**overrides))}",
                allow_redirects=False,
            )
            # Errors are shown on the page, never sent to the redirect URI.
            self.assertEqual(response.status_code, 200, overrides)
            self.assertIn("alert-danger", response.text)
            self.assertNotIn('name="csrf_token"', response.text)

    def test_unknown_params_not_forwarded(self):
        self.authenticate("mcp_oauth_user", "mcp_oauth_user")
        response = self.url_open(
            f"/mcp/{self.server.key}/oauth/authorize?"
            + urlencode(self._authorize_params(foo="bar"))
        )
        self.assertIn('name="csrf_token"', response.text)
        self.assertNotIn('name="foo"', response.text)

    def test_user_not_allowed(self):
        # Internal users need the group, portal users are never allowed.
        for login in ("mcp_oauth_no_group", "mcp_oauth_portal"):
            self.authenticate(login, login)
            response = self.url_open(
                f"/mcp/{self.server.key}/oauth/authorize?"
                + urlencode(self._authorize_params())
            )
            self.assertIn("You are not allowed", response.text, login)
            self.assertNotIn('name="csrf_token"', response.text, login)

    def test_user_removed_from_group(self):
        code = self._get_code()
        self.user.groups_id -= self.env.ref("ai_oca_mcp_oauth.group_mcp_oauth")
        response = self._token(code)
        self.assertEqual(response.json()["error"], "invalid_grant")
