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
GROUP = "ai_oca_mcp_oauth.group_mcp_oauth"


@tagged("post_install", "-at_install")
class TestMcpOAuth(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Odoo 16 may keep a routing map built by the at_install tests of a
        # module loaded before this one, without the routes of this module.
        cls.env["ir.http"]._clear_routing_map()
        cls.server = cls._create_server("Test Server")
        cls.authorize_path = f"/mcp/{cls.server.key}/oauth/authorize"
        cls.group = cls.env.ref(GROUP)
        cls.user = new_test_user(
            cls.env, login="mcp_oauth_user", groups=f"base.group_user,{GROUP}"
        )
        cls.user_no_group = new_test_user(cls.env, login="mcp_oauth_no_group")
        new_test_user(
            cls.env, login="mcp_oauth_portal", groups=f"base.group_portal,{GROUP}"
        )
        digest = hashlib.sha256(CODE_VERIFIER.encode()).digest()
        cls.code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    @classmethod
    def _create_server(cls, name, oauth_enabled=True):
        tool = cls.env.ref("ai_tool.current_date")
        return cls.env["mcp.server"].create(
            {
                "name": name,
                "tool_ids": [Command.link(tool.id)],
                "oauth_enabled": oauth_enabled,
            }
        )

    def setUp(self):
        super().setUp()
        self.client_id = self._register().json()["client_id"]

    def _post_json(self, path, payload, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.url_open(path, data=json.dumps(payload), headers=headers)

    def _register(self, redirect_uri=REDIRECT_URI, server=None):
        return self._post_json(
            f"/mcp/{(server or self.server).key}/oauth/register",
            {"client_name": "Claude", "redirect_uris": [redirect_uri]},
        )

    def _mcp(self, token=None, method="initialize", server=None):
        return self._post_json(
            f"/mcp/{(server or self.server).key}",
            {"jsonrpc": "2.0", "id": "1", "method": method},
            token,
        )

    def _create_key(self, token, user, **vals):
        server_key_model = self.env["mcp.server.key"]
        return server_key_model.create(
            {
                "name": "Manual",
                "server_id": self.server.id,
                "user_id": user.id,
                "hashed_key": server_key_model._hash_key(token),
                **vals,
            }
        )

    def _authorize_params(self, **overrides):
        return {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": REDIRECT_URI,
            "state": "test-state",
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
            **overrides,
        }

    def _authorize_url(self, **overrides):
        return f"{self.authorize_path}?{urlencode(self._authorize_params(**overrides))}"

    def _consent(self, approve=True):
        """Allow or deny on the consent page, return the query sent to the client."""
        self.authenticate("mcp_oauth_user", "mcp_oauth_user")
        page = self.url_open(self._authorize_url())
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        data = dict(self._authorize_params(), csrf_token=csrf_token.group(1))
        if approve:
            data["approve"] = "1"
        response = self.url_open(self.authorize_path, data=data, allow_redirects=False)
        location = urlsplit(response.headers["Location"])
        self.assertEqual(location._replace(query="").geturl(), REDIRECT_URI)
        query = parse_qs(location.query)
        self.assertEqual(query["state"], ["test-state"])
        self.assertEqual(query["iss"], [self.server.url])
        return query

    def _token(self, auth_code, server=None, **overrides):
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": self.client_id,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            **overrides,
        }
        return self.url_open(
            f"/mcp/{(server or self.server).key}/oauth/token", data=data
        )

    def _get_token(self):
        response = self._token(self._consent()["code"][0])
        self.assertEqual(response.status_code, 200)
        self.env.invalidate_all()
        return response.json()["access_token"]

    @mute_logger("odoo.http")
    def test_server_without_oauth(self):
        # Without OAuth, ai_oca_mcp answers as before.
        server = self._create_server("No OAuth", oauth_enabled=False)
        response = self._mcp("wrong", server=server)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WWW-Authenticate", response.headers)
        response = self.url_open(
            f"/.well-known/oauth-protected-resource/mcp/{server.key}"
        )
        self.assertEqual(response.status_code, 404)

    def test_discovery(self):
        # Follow the URLs as a client does, from the 401 to the endpoints.
        expired = fields.Datetime.now() - timedelta(days=1)
        self._create_key("expired-key", self.user, expiration_date=expired)
        for token in (None, "wrong", "expired-key"):
            response = self._mcp(token)
            self.assertEqual(response.status_code, 401, token)
            header = response.headers["WWW-Authenticate"]
            metadata_url = re.search(r'resource_metadata="([^"]+)"', header).group(1)
        resource = self.url_open(urlsplit(metadata_url).path).json()
        self.assertEqual(resource["resource"], self.server.url)
        self.assertEqual(resource["authorization_servers"], [self.server.url])
        issuer_path = urlsplit(self.server.url).path
        metadata = self.url_open(
            f"/.well-known/oauth-authorization-server{issuer_path}"
        ).json()
        self.assertEqual(metadata["issuer"], self.server.url)
        self.assertEqual(metadata["token_endpoint"], f"{self.server.url}/oauth/token")
        self.assertEqual(metadata["code_challenge_methods_supported"], ["S256"])
        self.assertTrue(metadata["authorization_response_iss_parameter_supported"])

    def test_register_redirect_uris(self):
        # The parameter adds to the Claude URIs; loopback URIs ignore the port only.
        self.env["ir.config_parameter"].set_param(
            "ai_oca_mcp_oauth.redirect_uris", "https://client.example.com/cb"
        )
        for redirect_uri, status in (
            (REDIRECT_URI, 201),
            ("http://localhost:4567/callback", 201),
            ("https://client.example.com/cb", 201),
            ("https://evil.example.com/callback", 400),
            ("http://localhost:4567/other", 400),
            ("http://localhost:4567@evil.example.com/callback", 400),
            ("http://localhost:4567/callback#fragment", 400),
            (f"{REDIRECT_URI}#fragment", 400),
        ):
            response = self._register(redirect_uri)
            self.assertEqual(response.status_code, status, redirect_uri)

    def test_consent_page(self):
        # Errors are shown on the page, never sent to the redirect URI.
        response = self.url_open(self._authorize_url(), allow_redirects=False)
        self.assertIn("/web/login?redirect=", response.headers["Location"])
        other_server = self._create_server("Other Server")
        other_client_id = self._register(server=other_server).json()["client_id"]
        self.authenticate("mcp_oauth_user", "mcp_oauth_user")
        page = self.url_open(self._authorize_url(foo="bar"))
        self.assertIn('name="csrf_token"', page.text)
        self.assertIn("<dd>Claude</dd>", page.text)
        self.assertNotIn('name="foo"', page.text)
        for overrides in (
            {"redirect_uri": "https://evil.example.com/callback"},
            # Allowed, but not among the URIs this client registered.
            {"redirect_uri": "http://localhost:4567/callback"},
            {"client_id": "forged-client"},
            {"client_id": other_client_id},
            {"code_challenge_method": "plain"},
            {"code_challenge": ""},
            {"response_type": "token"},
        ):
            page = self.url_open(
                self._authorize_url(**overrides), allow_redirects=False
            )
            self.assertEqual(page.status_code, 200, overrides)
            self.assertIn("alert-danger", page.text)
            self.assertNotIn('name="csrf_token"', page.text)
        for login in ("mcp_oauth_no_group", "mcp_oauth_portal"):
            self.authenticate(login, login)
            page = self.url_open(self._authorize_url())
            self.assertIn("You are not allowed", page.text, login)

    def test_full_flow(self):
        query = self._consent(approve=False)
        self.assertEqual(query["error"], ["access_denied"])
        self.assertNotIn("code", query)
        response = self._token(self._consent()["code"][0])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.env.invalidate_all()
        server_key = self.server.key_ids
        self.assertEqual(server_key.name, "Claude (claude.ai)")
        self.assertEqual(server_key.user_id, self.user)
        self.assertTrue(server_key.expiration_date)
        response = self._mcp(response.json()["access_token"], method="tools/list")
        self.assertEqual(
            response.json()["result"]["tools"][0]["name"],
            self.env.ref("ai_tool.current_date").name,
        )
        # Two consents in the same second give two codes, not a replay.
        with freeze_time(fields.Datetime.now()):
            self.assertNotEqual(self._consent()["code"], self._consent()["code"])

    def test_token_errors(self):
        code = self._consent()["code"][0]
        self.user.groups_id -= self.group
        self.assertEqual(self._token(code).json()["error"], "invalid_grant")
        self.user.groups_id += self.group
        for overrides in (
            {"code_verifier": "wrong-verifier"},
            {"redirect_uri": "http://localhost/callback"},
            {"client_id": "other-client"},
            {"code": code[:-1]},
            {"server": self._create_server("Other Server")},
        ):
            response = self._token(code, **overrides)
            self.assertEqual(response.status_code, 400, overrides)
            self.assertEqual(response.json()["error"], "invalid_grant")
        response = self._token(code, grant_type="refresh_token")
        self.assertEqual(response.json()["error"], "unsupported_grant_type")
        with patch.object(oauth, "CODE_LIFETIME", -1):
            expired_code = self._consent()["code"][0]
        self.assertEqual(self._token(expired_code).json()["error"], "invalid_grant")
        self.env.invalidate_all()
        self.assertFalse(self.server.key_ids)
        # A code used twice may have been stolen: the key it gave is expired.
        self.assertEqual(self._token(code).status_code, 200)
        self.assertEqual(self._token(code).json()["error"], "invalid_grant")
        self.env.invalidate_all()
        self.assertEqual(self.server.key_ids.state, "expired")

    def test_code_redeemed_concurrently(self):
        # The other request has created its key but not committed it yet, so
        # the search does not see it: the unique constraint stops this one.
        code_hash = self.env["mcp.server.key"]._hash_key("code")
        self._create_key("other-token", self.user, oauth_code_hash=code_hash)
        empty = self.env["mcp.server.key"]
        with patch.object(
            self.registry["mcp.server.key"], "search", return_value=empty
        ):
            token = self.server._oauth_issue_key(
                self.user, "code", "Claude", "claude.ai"
            )
        self.assertIsNone(token)
        self.assertEqual(len(self.server.key_ids), 1)

    def test_token_on_mcp_endpoint(self):
        # A key added by hand is not bound to the OAuth group, an OAuth key is.
        self._create_key("manual-key", self.user_no_group)
        self.assertEqual(self._mcp("manual-key").status_code, 200)
        token = self._get_token()
        self.assertEqual(self._mcp(token).status_code, 200)
        self.user.active = False
        self.assertEqual(self._mcp(token).status_code, 401)
        self.user.active = True
        self.user.groups_id -= self.group
        self.assertEqual(self._mcp(token).status_code, 401)
        self.user.groups_id += self.group
        self.assertEqual(self._mcp(token).status_code, 200)
        with freeze_time(fields.Datetime.now() + timedelta(days=31)):
            self.assertEqual(self._mcp(token).status_code, 401)
        self.env.invalidate_all()
        self.assertEqual(self.server.key_ids.filtered("is_oauth").state, "expired")

    def test_disconnect_from_preferences(self):
        self._get_token()
        server_key = self.server.key_ids
        user_data = self.user.with_user(self.user).read(["mcp_oauth_key_ids"])[0]
        self.assertEqual(user_data["mcp_oauth_key_ids"], server_key.ids)
        # Past its expiration date, a key no client has used since is still
        # active, but no longer listed.
        server_key.expiration_date = fields.Datetime.now() - timedelta(days=1)
        self.env.invalidate_all()
        self.assertFalse(self.user.mcp_oauth_key_ids)
        with self.assertRaises(AccessError):
            server_key.with_user(self.user_no_group).action_disconnect()
        server_key.with_user(self.user).action_disconnect()
        self.assertEqual(server_key.state, "expired")

    def test_oauth_keys_expire_with_oauth(self):
        # Turning OAuth off, or uninstalling, expires OAuth keys only.
        manual_key = self._create_key("manual-key", self.user)
        self._get_token()
        self.server.oauth_enabled = False
        self.assertEqual((self.server.key_ids - manual_key).state, "expired")
        self.server.oauth_enabled = True
        self._get_token()
        uninstall_hook(self.env.cr, self.registry)
        oauth_keys = self.server.key_ids - manual_key
        self.assertEqual(set(oauth_keys.mapped("state")), {"expired"})
        self.assertEqual(manual_key.state, "active")

    @mute_logger("odoo.addons.ai_oca_mcp_oauth.models.mcp_server")
    def test_invalid_token_lifetime_falls_back(self):
        # A mistyped parameter must not break every token exchange.
        for value in ("30d", "0", "-5"):
            self.env["ir.config_parameter"].set_param(
                "ai_oca_mcp_oauth.token_lifetime_days", value
            )
            self.assertEqual(self.server._get_oauth_token_lifetime_days(), 30, value)
