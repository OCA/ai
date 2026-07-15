# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger


class TestMcp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = cls.env["mcp.server"].create(
            {
                "name": "Test Server",
                "tool_ids": [(4, cls.env.ref("ai_tool.current_date").id)],
            }
        )
        wizard = (
            cls.env["mcp.server.key.add"]
            .with_context(default_server_id=cls.server.id)
            .create({"name": "Test Key"})
        )
        wizard.generate_key()
        cls.security_key = wizard.key

    @mute_logger("odoo.http")
    def test_no_authorization(self):
        request = self.url_open(
            f"/mcp/{self.server.key}",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "initialize",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(request.status_code, 401)

    def test_wrong_authorization(self):
        request = self.url_open(
            f"/mcp/{self.server.key}",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "initialize",
                }
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer wrong",
            },
        )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertIn("error", response)

    def test_wrong_method(self):
        request = self.url_open(
            f"/mcp/{self.server.key}",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "wrong_method",
                }
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.security_key}",
            },
        )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertIn("error", response)

    def test_correct_initialize(self):
        request = self.url_open(
            f"/mcp/{self.server.key}",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "initialize",
                }
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.security_key}",
            },
        )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertIn("result", response)
        self.assertIn("capabilities", response["result"])
        self.assertIn("tools", response["result"]["capabilities"])

    def test_list_tools(self):
        request = self.url_open(
            f"/mcp/{self.server.key}",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/list",
                }
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.security_key}",
            },
        )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertIn("result", response)
        self.assertIn("tools", response["result"])
        self.assertEqual(1, len(response["result"]["tools"]))
        self.assertEqual("get_date", response["result"]["tools"][0]["name"])

    def test_execute_wrong_tool(self):
        with freeze_time("2024-01-01"):
            request = self.url_open(
                f"/mcp/{self.server.key}",
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "tools/call",
                        "params": {
                            "name": "post_message",
                            "arguments": {},
                        },
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.security_key}",
                },
            )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertIn("error", response)

    def test_execute_tool(self):
        with freeze_time("2024-01-01"):
            request = self.url_open(
                f"/mcp/{self.server.key}",
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "tools/call",
                        "params": {
                            "name": "get_date",
                            "arguments": {},
                        },
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.security_key}",
                },
            )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertIn("result", response)
        self.assertIn("structuredContent", response["result"])
        self.assertEqual(response["result"]["structuredContent"]["date"], "2024-01-01")

    @mute_logger("odoo.models", "odoo.addons.base.models.ir_rule")
    def test_internal_user_access(self):
        """A plain internal user can read the key (and its server) it owns,
        but cannot open records for which it has no key of its own."""
        group_user = self.env.ref("base.group_user")
        user_a = self.env["res.users"].create(
            {
                "name": "MCP User A",
                "login": "mcp_user_a",
                "groups_id": [(6, 0, [group_user.id])],
            }
        )
        user_b = self.env["res.users"].create(
            {
                "name": "MCP User B",
                "login": "mcp_user_b",
                "groups_id": [(6, 0, [group_user.id])],
            }
        )
        self.assertFalse(user_a.has_group("base.group_system"))
        # user_a owns a key on self.server
        key_a = self.env["mcp.server.key"].create(
            {"name": "Key A", "server_id": self.server.id, "user_id": user_a.id}
        )
        # user_b owns a key on another server; user_a has no key anywhere on it
        other_server = self.env["mcp.server"].create({"name": "Other Server"})
        key_b = self.env["mcp.server.key"].create(
            {"name": "Key B", "server_id": other_server.id, "user_id": user_b.id}
        )

        # --- With a key of its own, the internal user can read it and its server ---
        self.assertEqual(key_a.with_user(user_a).read(["name"])[0]["name"], "Key A")
        self.assertEqual(
            self.server.with_user(user_a).read(["name"])[0]["name"], "Test Server"
        )
        self.assertIn(key_a, self.env["mcp.server.key"].with_user(user_a).search([]))
        self.assertIn(self.server, self.env["mcp.server"].with_user(user_a).search([]))

        # --- Records it has no key for are filtered out and cannot be opened ---
        self.assertNotIn(key_b, self.env["mcp.server.key"].with_user(user_a).search([]))
        self.assertNotIn(
            other_server, self.env["mcp.server"].with_user(user_a).search([])
        )
        with self.assertRaises(AccessError):
            key_b.with_user(user_a).read(["name"])
        with self.assertRaises(AccessError):
            other_server.with_user(user_a).read(["name"])

    def _create_non_admin_key(self):
        """Create an active key on self.server owned by a plain internal user
        (base.group_user only) and return its security key."""
        user = self.env["res.users"].create(
            {
                "name": "MCP Plain User",
                "login": "mcp_plain_user",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.assertFalse(user.has_group("base.group_system"))
        key = self.env["mcp.server.key"].create(
            {"name": "Plain Key", "server_id": self.server.id, "user_id": user.id}
        )
        security_key = "plain-user-security-key"
        key.hashed_key = key._hash_key(security_key)
        # Refresh the cached key lookup so the new key is resolvable.
        self.env["mcp.server.key"]._get_mcp_server_by_key.clear_cache(
            self.env["mcp.server.key"]
        )
        return security_key

    def test_list_tools_non_admin_user(self):
        """A key owned by a plain internal user (no ir.model access) must still
        be able to list tools -- building the tool definitions must not require
        Administration/Access Rights."""
        security_key = self._create_non_admin_key()
        request = self.url_open(
            f"/mcp/{self.server.key}",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/list",
                }
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {security_key}",
            },
        )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertNotIn("error", response)
        self.assertIn("result", response)
        self.assertEqual(1, len(response["result"]["tools"]))
        self.assertEqual("get_date", response["result"]["tools"][0]["name"])

    def test_execute_tool_non_admin_user(self):
        """A generic tool must be callable through a plain internal user's key
        (its model dispatch must not require ir.model read access)."""
        security_key = self._create_non_admin_key()
        with freeze_time("2024-01-01"):
            request = self.url_open(
                f"/mcp/{self.server.key}",
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "tools/call",
                        "params": {
                            "name": "get_date",
                            "arguments": {},
                        },
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {security_key}",
                },
            )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertNotIn("error", response)
        self.assertIn("result", response)
        self.assertEqual(response["result"]["structuredContent"]["date"], "2024-01-01")

    def test_url(self):
        self.server.key = "newkey"
        self.assertEqual(self.server.url, "http://127.0.0.1:8069/mcp/newkey")

    def test_expiration_handling(self):
        self.server.key_ids.write({"expiration_date": "2024-01-02 00:00:00"})
        with freeze_time("2024-01-01"):
            request = self.url_open(
                f"/mcp/{self.server.key}",
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "initialize",
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.security_key}",
                },
            )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertIn("result", response)
        self.assertNotIn("error", response)
        with freeze_time("2024-01-03"):
            request = self.url_open(
                f"/mcp/{self.server.key}",
                data=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "initialize",
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.security_key}",
                },
            )
        self.assertEqual(request.status_code, 200)
        response = json.loads(request.content.decode("utf-8"))
        self.assertNotIn("result", response)
        self.assertIn("error", response)
