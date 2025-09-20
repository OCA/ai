#!/usr/bin/env python3
"""
Mock MCP server for basic tests.
This server implements the MCP protocol to provide basic test tools and resources.
"""


from mcp.server.fastmcp import FastMCP


def create_mock_server() -> FastMCP:
    """Create a mock MCP server for testing."""
    mcp = FastMCP("Test Server")

    @mcp.tool()
    def basic_tool(param: str) -> str:
        """Basic tool for testing."""
        return f"Basic tool result: {param}"

    @mcp.tool()
    def math_add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @mcp.resource("test://basic/{resource_id}")
    def get_basic_resource(resource_id: str) -> str:
        """Get a basic resource by ID."""
        return f"Basic resource {resource_id} content"

    return mcp


def main():
    """Run the mock MCP server."""
    server = create_mock_server()

    # Run the server using stdio transport
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
