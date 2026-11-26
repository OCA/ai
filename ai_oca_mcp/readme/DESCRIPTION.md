This module exposes Odoo AI tools as an MCP (Model Context Protocol) server, 
allowing external AI clients such as n8n or custom agents to call Odoo functions 
via the standardized MCP protocol. Authentication is handled via per-client API keys.

Note: Claude Desktop requires OAuth 2.0, which is not supported directly by this module.
An extension could be required.
