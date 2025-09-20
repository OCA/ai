# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestMcpServer(TransactionCase):
    def setUp(self):
        super().setUp()
        # Get the path to the mock server
        import os

        mock_server_path = os.path.join(
            os.path.dirname(__file__), "mock_servers", "test_server.py"
        )

        self.server = self.env["mcp.server"].create(
            {
                "name": "Test Server",
                "description": "Test MCP Server",
                "command": "python",
                "args": f'["{mock_server_path}"]',
                "env_vars": '{"TEST_VAR": "test_value"}',
            }
        )

    def test_server_creation(self):
        """Test MCP server creation"""
        self.assertEqual(self.server.name, "Test Server")
        self.assertEqual(self.server.command, "python")
        # Check that args contains the mock server path
        self.assertIn("mock_servers/test_server.py", self.server.args)
        self.assertEqual(self.server.env_vars, '{"TEST_VAR": "test_value"}')
        self.assertTrue(self.server.active)
        self.assertFalse(self.server.enabled)
        self.assertEqual(self.server.state, "stopped")

    def test_server_json_fields(self):
        """Test MCP server JSON fields"""
        # Test valid JSON args
        self.server.args = '["arg1", "arg2"]'
        self.server.env_vars = '{"key": "value"}'
        self.assertEqual(self.server.args, '["arg1", "arg2"]')
        self.assertEqual(self.server.env_vars, '{"key": "value"}')

    def test_server_toggle_active(self):
        """Test server active toggle"""
        self.assertTrue(self.server.active)
        self.server.active = False
        self.assertFalse(self.server.active)

    def test_server_toggle_enabled(self):
        """Test server enabled toggle"""
        self.assertFalse(self.server.enabled)
        self.server.enabled = True
        self.assertTrue(self.server.enabled)

    def test_server_state_transitions(self):
        """Test server state field"""
        self.assertEqual(self.server.state, "stopped")
        self.server.state = "running"
        self.assertEqual(self.server.state, "running")
        self.server.state = "error"
        self.assertEqual(self.server.state, "error")

    def test_server_auto_approve_field(self):
        """Test auto_approve field"""
        self.server.auto_approve = '["tool1", "tool2"]'
        self.assertEqual(self.server.auto_approve, '["tool1", "tool2"]')

    def test_server_invalid_json_args(self):
        """Test server with invalid JSON args"""
        with self.assertRaises(ValidationError):
            self.env["mcp.server"].create(
                {
                    "name": "Invalid Server",
                    "command": "python",
                    "args": "invalid json",
                }
            )

    def test_server_invalid_json_env_vars(self):
        """Test server with invalid JSON env_vars"""
        with self.assertRaises(ValidationError):
            self.env["mcp.server"].create(
                {
                    "name": "Invalid Server",
                    "command": "python",
                    "args": '["test.py"]',
                    "env_vars": "invalid json",
                }
            )

    def test_server_invalid_json_auto_approve(self):
        """Test server with invalid JSON auto_approve"""
        with self.assertRaises(ValidationError):
            self.env["mcp.server"].create(
                {
                    "name": "Invalid Server",
                    "command": "python",
                    "args": '["test.py"]',
                    "auto_approve": "invalid json",
                }
            )

    def test_server_json_validation_args(self):
        """Test JSON validation for args field"""
        # Valid JSON array
        self.server.args = '["arg1", "arg2", "arg3"]'
        self.server._check_json_fields()

        # Invalid JSON (not an array)
        with self.assertRaises(ValidationError):
            self.server.args = '{"not": "array"}'

    def test_server_json_validation_env_vars(self):
        """Test JSON validation for env_vars field"""
        # Valid JSON object
        self.server.env_vars = '{"KEY1": "value1", "KEY2": "value2"}'
        self.server._check_json_fields()

        # Invalid JSON (not an object)
        with self.assertRaises(ValidationError):
            self.server.env_vars = '["not", "object"]'

    def test_server_json_validation_auto_approve(self):
        """Test JSON validation for auto_approve field"""
        # Valid JSON array
        self.server.auto_approve = '["tool1", "tool2"]'
        self.server._check_json_fields()

        # Invalid JSON (not an array)
        with self.assertRaises(ValidationError):
            self.server.auto_approve = '{"not": "array"}'

    def test_server_tool_count(self):
        """Test server tool count computation"""
        # Initially no tools
        self.assertEqual(self.server.tool_count, 0)

        # Create a tool
        self.env["mcp.tool"].create(
            {
                "name": "test_tool",
                "description": "Test Tool",
                "server_id": self.server.id,
                "input_schema": '{"type": "object"}',
            }
        )

        # Refresh the count
        self.server._compute_tool_count()
        self.assertEqual(self.server.tool_count, 1)

    def test_server_resource_count(self):
        """Test server resource count computation"""
        # Initially no resources
        self.assertEqual(self.server.resource_count, 0)

        # Create a resource
        self.env["mcp.resource"].create(
            {
                "name": "test_resource",
                "description": "Test Resource",
                "server_id": self.server.id,
                "uri": "test://resource",
                "mime_type": "text/plain",
            }
        )

        # Refresh the count
        self.server._compute_resource_count()
        self.assertEqual(self.server.resource_count, 1)

    def test_server_action_start(self):
        """Test server start action"""
        # Test starting server
        result = self.server.action_start()

        # Check that it returns a notification action
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["title"], "Server Started")

    def test_server_action_stop(self):
        """Test server stop action"""
        # Set server to running first
        self.server.state = "running"

        # Test stopping server
        result = self.server.action_stop()

        # Check that it returns a notification action
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["title"], "Server Stopped")
