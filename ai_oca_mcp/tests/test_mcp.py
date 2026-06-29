# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from freezegun import freeze_time

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

    def test_execute_tool_returns_error_when_tool_execution_raises_exception(self):
        from unittest.mock import patch

        with patch(
            "odoo.addons.ai_tool.models.ai_tool.AiTool._execute_tool",
            side_effect=Exception("Test execution error"),
        ):
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
        self.assertNotIn("result", response)
        self.assertIn("error", response)
        self.assertEqual(response["error"]["message"], "Test execution error")

        log = self.env["mcp.server.log"].search(
            [("server_id", "=", self.server.id)], order="id desc", limit=1
        )
        self.assertTrue(log)
        self.assertEqual(log.error, "Test execution error")

    def test_url(self):
        self.server.key = "newkey"
        self.assertEqual(self.server.url, f"{self.base_url()}/mcp/newkey")

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
        self.assertEqual(request.status_code, 200, request.content.decode("utf-8"))
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
        self.assertEqual(request.status_code, 200, request.content.decode("utf-8"))
        response = json.loads(request.content.decode("utf-8"))
        self.assertNotIn("result", response)
        self.assertIn("error", response)
