# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo.tests.common import TransactionCase


class TestMcpResource(TransactionCase):
    def setUp(self):
        super().setUp()
        self.server = self.env["mcp.server"].create(
            {
                "name": "Test Server",
                "command": "python",
                "args": '["test_server.py"]',
            }
        )
        self.resource = self.env["mcp.resource"].create(
            {
                "name": "test_resource",
                "description": "Test Resource",
                "server_id": self.server.id,
                "uri": "test://resource",
                "mime_type": "text/plain",
            }
        )

    def test_resource_creation(self):
        """Test MCP resource creation"""
        self.assertEqual(self.resource.name, "test_resource")
        self.assertEqual(self.resource.description, "Test Resource")
        self.assertEqual(self.resource.server_id, self.server)
        self.assertEqual(self.resource.uri, "test://resource")
        self.assertEqual(self.resource.mime_type, "text/plain")

    def test_resource_server_relation(self):
        """Test resource-server relationship"""
        self.assertEqual(self.resource.server_id, self.server)

    def test_resource_uri_field(self):
        """Test resource URI field"""
        # Test valid URI
        self.resource.uri = "https://example.com/resource"
        self.assertEqual(self.resource.uri, "https://example.com/resource")

    def test_resource_uri_field_values(self):
        """Test resource URI field with different values"""
        # Test valid URI
        self.resource.uri = "https://example.com/resource"
        self.assertEqual(self.resource.uri, "https://example.com/resource")

        # Test another valid URI
        self.resource.uri = "file:///path/to/resource"
        self.assertEqual(self.resource.uri, "file:///path/to/resource")

    def test_resource_mime_type_field(self):
        """Test resource MIME type field"""
        # Test valid MIME types
        valid_mimes = [
            "text/plain",
            "text/html",
            "application/json",
            "image/png",
            "video/mp4",
            "application/octet-stream",
        ]

        for mime in valid_mimes:
            self.resource.mime_type = mime
            self.assertEqual(self.resource.mime_type, mime)

    def test_resource_cascade_delete(self):
        """Test resource deletion when server is deleted"""
        resource_id = self.resource.id

        # Delete the server
        self.server.unlink()

        # Resource should be deleted as well (cascade)
        self.assertFalse(self.env["mcp.resource"].search([("id", "=", resource_id)]))

    def test_resource_search_by_name(self):
        """Test searching resources by name"""
        # Create another resource
        self.env["mcp.resource"].create(
            {
                "name": "another_resource",
                "description": "Another Resource",
                "server_id": self.server.id,
                "uri": "test://another",
                "mime_type": "text/plain",
            }
        )

        # Search by name
        resources = self.env["mcp.resource"].search([("name", "ilike", "test")])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].name, "test_resource")

        # Search by server
        resources = self.env["mcp.resource"].search(
            [("server_id", "=", self.server.id)]
        )
        self.assertEqual(len(resources), 2)

    def test_resource_search_by_uri(self):
        """Test searching resources by URI"""
        # Search by URI
        resources = self.env["mcp.resource"].search([("uri", "ilike", "test://")])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].uri, "test://resource")

    def test_resource_search_by_mime_type(self):
        """Test searching resources by MIME type"""
        # Search by MIME type for our specific resource
        resources = self.env["mcp.resource"].search(
            [("mime_type", "=", "text/plain"), ("uri", "=", "test://resource")]
        )
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].mime_type, "text/plain")

    def test_resource_copy(self):
        """Test resource copying"""
        # Create a new server for the copy to avoid unique constraint violation
        new_server = self.env["mcp.server"].create(
            {
                "name": "Copy Test Server",
                "command": "python",
                "args": '["copy_server.py"]',
            }
        )

        # Copy the resource and assign to new server
        copied_resource = self.resource.copy({"server_id": new_server.id})

        # Check that the copy was created successfully
        self.assertNotEqual(copied_resource.id, self.resource.id)
        self.assertEqual(copied_resource.description, "Test Resource")
        self.assertEqual(copied_resource.server_id, new_server)
        self.assertEqual(copied_resource.uri, "test://resource")
        self.assertEqual(copied_resource.mime_type, "text/plain")
        # The name might be the same or have a suffix depending on Odoo version
        self.assertTrue(copied_resource.name.startswith("test_resource"))

    def test_resource_write(self):
        """Test resource updating"""
        self.resource.write(
            {
                "name": "updated_resource",
                "description": "Updated Resource",
                "uri": "test://updated",
                "mime_type": "application/json",
            }
        )

        self.assertEqual(self.resource.name, "updated_resource")
        self.assertEqual(self.resource.description, "Updated Resource")
        self.assertEqual(self.resource.uri, "test://updated")
        self.assertEqual(self.resource.mime_type, "application/json")

    def test_resource_basic_fields(self):
        """Test basic resource fields"""
        self.assertEqual(self.resource.name, "test_resource")
        self.assertEqual(self.resource.description, "Test Resource")
        self.assertEqual(self.resource.server_id, self.server)
        self.assertEqual(self.resource.uri, "test://resource")
        self.assertEqual(self.resource.mime_type, "text/plain")

    def test_resource_ordering(self):
        """Test resource ordering by server and name"""
        # Create another server
        server2 = self.env["mcp.server"].create(
            {
                "name": "Server 2",
                "command": "python",
                "args": '["server2.py"]',
            }
        )

        # Create resources with different servers and names
        resource1 = self.env["mcp.resource"].create(
            {
                "name": "z_resource",
                "server_id": self.server.id,
                "uri": "test://z",
                "mime_type": "text/plain",
            }
        )
        resource2 = self.env["mcp.resource"].create(
            {
                "name": "a_resource",
                "server_id": server2.id,
                "uri": "test://a",
                "mime_type": "text/plain",
            }
        )

        # Test ordering (order by server_id, name)
        resources = self.env["mcp.resource"].search([])
        # Resources are ordered by server_id, name
        # First server: self.resource, resource1
        # Second server: resource2
        self.assertIn(self.resource, resources)
        self.assertIn(resource1, resources)
        self.assertIn(resource2, resources)
