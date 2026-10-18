# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA MCP OAuth",
    "summary": "Let MCP clients such as Claude get a key by signing in to Odoo",
    "version": "16.0.1.0.0",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "author": "Quartile,Odoo Community Association (OCA)",
    "maintainers": ["nobuQuartile"],
    "depends": [
        "ai_oca_mcp",
    ],
    "data": [
        "security/security.xml",
        "views/mcp_server_views.xml",
        "views/templates.xml",
        "views/res_users_views.xml",
    ],
    "uninstall_hook": "uninstall_hook",
}
