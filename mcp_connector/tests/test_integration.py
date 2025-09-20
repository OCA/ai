# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestMcpIntegration(TransactionCase):
    """Integration tests for MCP Connector module"""

    def setUp(self):
        super().setUp()
        # Get the path to the mock server
        import os

        mock_server_path = os.path.join(
            os.path.dirname(__file__), "mock_servers", "integration_server.py"
        )

        self.server = self.env["mcp.server"].create(
            {
                "name": "Integration Test Server",
                "description": "Server for integration tests",
                "command": "python",
                "args": f'["{mock_server_path}"]',
                "env_vars": '{"TEST_MODE": "true", "DEBUG": "1"}',
                "auto_approve": '["test_tool", "read_file"]',
            }
        )

    def test_server_tool_resource_integration(self):
        """Test complete integration between server, tools, and resources"""
        # Create tools
        tool1 = self.env["mcp.tool"].create(
            {
                "name": "test_tool",
                "description": "Test Tool for Integration",
                "server_id": self.server.id,
                "input_schema": (
                    '{"type": "object", "properties": {"input": {"type": "string"}}}'
                ),
            }
        )

        tool2 = self.env["mcp.tool"].create(
            {
                "name": "read_file",
                "description": "Read File Tool",
                "server_id": self.server.id,
                "input_schema": (
                    '{"type": "object", "properties": {"filename": {"type": "string"}}}'
                ),
            }
        )

        # Create resources
        resource1 = self.env["mcp.resource"].create(
            {
                "name": "config_file",
                "description": "Configuration File",
                "server_id": self.server.id,
                "uri": "file:///etc/config.json",
                "mime_type": "application/json",
            }
        )

        resource2 = self.env["mcp.resource"].create(
            {
                "name": "log_file",
                "description": "Log File",
                "server_id": self.server.id,
                "uri": "file:///var/log/app.log",
                "mime_type": "text/plain",
            }
        )

        # Test relationships
        self.assertEqual(tool1.server_id, self.server)
        self.assertEqual(tool2.server_id, self.server)
        self.assertEqual(resource1.server_id, self.server)
        self.assertEqual(resource2.server_id, self.server)

        # Test server counts
        self.server._compute_tool_count()
        self.server._compute_resource_count()
        self.assertEqual(self.server.tool_count, 2)
        self.assertEqual(self.server.resource_count, 2)

    def test_server_auto_approve_field(self):
        """Test server auto-approve field functionality"""
        # Test auto_approve field
        self.server.auto_approve = '["test_tool", "read_file"]'
        self.assertEqual(self.server.auto_approve, '["test_tool", "read_file"]')

        # Test JSON validation
        self.server._check_json_fields()

    def test_cascade_deletion_integration(self):
        """Test cascade deletion when server is deleted"""
        # Create tools and resources
        tool = self.env["mcp.tool"].create(
            {
                "name": "cascade_tool",
                "description": "Tool for cascade test",
                "server_id": self.server.id,
                "input_schema": '{"type": "object"}',
            }
        )

        resource = self.env["mcp.resource"].create(
            {
                "name": "cascade_resource",
                "description": "Resource for cascade test",
                "server_id": self.server.id,
                "uri": "test://cascade",
                "mime_type": "text/plain",
            }
        )

        tool_id = tool.id
        resource_id = resource.id

        # Delete server
        self.server.unlink()

        # Check that tools and resources are also deleted
        self.assertFalse(self.env["mcp.tool"].search([("id", "=", tool_id)]))
        self.assertFalse(self.env["mcp.resource"].search([("id", "=", resource_id)]))

    def test_server_state_management_integration(self):
        """Test server state management with tools and resources"""
        # Create tools and resources
        self.env["mcp.tool"].create(
            {
                "name": "state_tool",
                "description": "Tool for state test",
                "server_id": self.server.id,
                "input_schema": '{"type": "object"}',
            }
        )

        self.env["mcp.resource"].create(
            {
                "name": "state_resource",
                "description": "Resource for state test",
                "server_id": self.server.id,
                "uri": "test://state",
                "mime_type": "text/plain",
            }
        )

        # Test server state changes
        self.assertEqual(self.server.state, "stopped")

        # Test action_start
        result = self.server.action_start()
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")

        # Test action_stop
        self.server.state = "running"
        result = self.server.action_stop()
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")

    def test_error_handling_integration(self):
        """Test error handling across the integration"""
        # Test server creation with invalid data
        with self.assertRaises(ValidationError):
            self.env["mcp.server"].create(
                {
                    "name": "Invalid Server",
                    "command": "python",
                    "args": "invalid json",
                }
            )

    def test_multiple_tools_resources(self):
        """Test creating multiple tools and resources"""
        # Create multiple tools and resources
        tools = []
        resources = []

        for i in range(5):
            tool = self.env["mcp.tool"].create(
                {
                    "name": f"tool_{i}",
                    "description": f"Tool {i}",
                    "server_id": self.server.id,
                    "input_schema": '{"type": "object"}',
                }
            )
            tools.append(tool)

            resource = self.env["mcp.resource"].create(
                {
                    "name": f"resource_{i}",
                    "description": f"Resource {i}",
                    "server_id": self.server.id,
                    "uri": "test://resource_%d" % i,
                    "mime_type": "text/plain",
                }
            )
            resources.append(resource)

        # Test that all relationships are correct
        self.server._compute_tool_count()
        self.server._compute_resource_count()
        self.assertEqual(self.server.tool_count, 5)
        self.assertEqual(self.server.resource_count, 5)

        # Test search
        tools_found = self.env["mcp.tool"].search([("server_id", "=", self.server.id)])
        self.assertEqual(len(tools_found), 5)

        resources_found = self.env["mcp.resource"].search(
            [("server_id", "=", self.server.id)]
        )
        self.assertEqual(len(resources_found), 5)

    def test_data_consistency_integration(self):
        """Test data consistency across the integration"""
        # Create initial data
        tool = self.env["mcp.tool"].create(
            {
                "name": "consistency_tool",
                "description": "Tool for consistency test",
                "server_id": self.server.id,
                "input_schema": '{"type": "object"}',
            }
        )

        resource = self.env["mcp.resource"].create(
            {
                "name": "consistency_resource",
                "description": "Resource for consistency test",
                "server_id": self.server.id,
                "uri": "test://consistency",
                "mime_type": "text/plain",
            }
        )

        # Test that server counts are consistent
        self.server._compute_tool_count()
        self.server._compute_resource_count()
        self.assertEqual(self.server.tool_count, 1)
        self.assertEqual(self.server.resource_count, 1)

        # Update server name and test consistency
        self.server.write({"name": "Updated Server Name"})

        # Check that relationships are still intact
        self.assertEqual(tool.server_id.name, "Updated Server Name")
        self.assertEqual(resource.server_id.name, "Updated Server Name")
