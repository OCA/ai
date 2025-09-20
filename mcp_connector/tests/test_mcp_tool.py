# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestMcpTool(TransactionCase):
    def setUp(self):
        super().setUp()
        self.server = self.env["mcp.server"].create(
            {
                "name": "Test Server",
                "command": "python",
                "args": '["test_server.py"]',
            }
        )
        self.tool = self.env["mcp.tool"].create(
            {
                "name": "test_tool",
                "description": "Test Tool",
                "server_id": self.server.id,
                "input_schema": (
                    '{"type": "object", "properties": {"text": {"type": "string"}}}'
                ),
            }
        )

    def test_tool_creation(self):
        """Test MCP tool creation"""
        self.assertEqual(self.tool.name, "test_tool")
        self.assertEqual(self.tool.description, "Test Tool")
        self.assertEqual(self.tool.server_id, self.server)
        self.assertEqual(
            self.tool.input_schema,
            ('{"type": "object", "properties": {"text": {"type": "string"}}}'),
        )

    def test_tool_json_schema(self):
        """Test MCP tool JSON schema"""
        # Test valid JSON schema
        self.tool.input_schema = '{"type": "object"}'
        self.assertEqual(self.tool.input_schema, '{"type": "object"}')

    def test_tool_server_relation(self):
        """Test tool-server relationship"""
        self.assertEqual(self.tool.server_id, self.server)

    def test_tool_invalid_json_schema(self):
        """Test tool with invalid JSON schema"""
        with self.assertRaises(ValidationError):
            self.env["mcp.tool"].create(
                {
                    "name": "invalid_tool",
                    "description": "Tool with invalid schema",
                    "server_id": self.server.id,
                    "input_schema": "invalid json",
                }
            )

    def test_tool_json_validation(self):
        """Test JSON validation for input_schema field"""
        # Valid JSON schema
        self.tool.input_schema = (
            '{"type": "object", "properties": {"name": {"type": "string"}}}'
        )
        # The validation happens automatically on write

        # Invalid JSON
        with self.assertRaises(ValidationError):
            self.tool.input_schema = "invalid json"

    def test_tool_schema_validation(self):
        """Test schema validation for input_schema field"""
        # Valid JSON schema
        self.tool.input_schema = (
            '{"type": "object", "properties": {"name": {"type": "string"}}}'
        )
        # The validation happens automatically on write

        # Invalid JSON (not an object)
        with self.assertRaises(ValidationError):
            self.tool.input_schema = '["not", "object"]'

    def test_tool_cascade_delete(self):
        """Test tool deletion when server is deleted"""
        tool_id = self.tool.id

        # Delete the server
        self.server.unlink()

        # Tool should be deleted as well (cascade)
        self.assertFalse(self.env["mcp.tool"].search([("id", "=", tool_id)]))

    def test_tool_search_by_name(self):
        """Test searching tools by name"""
        # Create another tool
        self.env["mcp.tool"].create(
            {
                "name": "another_tool",
                "description": "Another Tool",
                "server_id": self.server.id,
                "input_schema": '{"type": "object"}',
            }
        )

        # Search by name
        tools = self.env["mcp.tool"].search([("name", "ilike", "test")])
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, "test_tool")

        # Search by server
        tools = self.env["mcp.tool"].search([("server_id", "=", self.server.id)])
        self.assertEqual(len(tools), 2)

    def test_tool_copy(self):
        """Test tool copying"""
        # Create a new server for the copy to avoid unique constraint violation
        new_server = self.env["mcp.server"].create(
            {
                "name": "Copy Test Server",
                "command": "python",
                "args": '["copy_server.py"]',
            }
        )

        # Copy the tool and assign to new server
        copied_tool = self.tool.copy({"server_id": new_server.id})

        # Check that the copy was created successfully
        self.assertNotEqual(copied_tool.id, self.tool.id)
        self.assertEqual(copied_tool.description, "Test Tool")
        self.assertEqual(copied_tool.server_id, new_server)
        self.assertEqual(copied_tool.input_schema, self.tool.input_schema)
        # The name might be the same or have a suffix depending on Odoo version
        self.assertTrue(copied_tool.name.startswith("test_tool"))

    def test_tool_write(self):
        """Test tool updating"""
        self.tool.write(
            {
                "name": "updated_tool",
                "description": "Updated Tool",
                "input_schema": (
                    '{"type": "object", "properties": {"new_field": {"type": "string"}}}'
                ),
            }
        )

        self.assertEqual(self.tool.name, "updated_tool")
        self.assertEqual(self.tool.description, "Updated Tool")
        self.assertIn("new_field", self.tool.input_schema)
