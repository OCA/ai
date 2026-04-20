# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Ai Oca Mcp",
    "summary": """MCP Interface for Odoo""",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Dixmit,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": [
        "ai_tool",
    ],
    "data": [
        "views/mcp_server_log.xml",
        "security/ir.model.access.csv",
        "views/mcp_server_key.xml",
        "wizards/mcp_server_key_add.xml",
        "views/mcp_server.xml",
    ],
    "demo": [],
}
