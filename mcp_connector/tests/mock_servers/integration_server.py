#!/usr/bin/env python3
"""
Mock MCP server for integration tests.
This server implements the MCP protocol to provide test tools and resources.
"""

import json

from mcp.server.fastmcp import FastMCP


def create_mock_server() -> FastMCP:
    """Create a mock MCP server for testing."""
    mcp = FastMCP("Integration Test Server")

    @mcp.tool()
    def test_tool(input_text: str) -> str:
        """Test tool for integration testing."""
        return f"Processed: {input_text}"

    @mcp.tool()
    def read_file(filename: str) -> str:
        """Read file tool for testing."""
        return f"File content of {filename}: Mock content"

    @mcp.resource("test://resource/{name}")
    def get_test_resource(name: str) -> str:
        """Get a test resource by name."""
        return f"Test resource content for {name}"

    @mcp.resource("config://settings")
    def get_settings() -> str:
        """Get application settings."""
        return json.dumps({"test_mode": True, "debug": True, "version": "1.0.0"})

    return mcp


def main():
    """Run the mock MCP server."""
    server = create_mock_server()

    # Run the server using stdio transport
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
