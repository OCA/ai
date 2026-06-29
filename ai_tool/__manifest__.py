# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Ai Tool",
    "summary": """We want to generate some specific AI Tools
    that might be used in other places, like MCP or native.""",
    "version": "17.0.1.0.0",
    "license": "AGPL-3",
    "author": "Dixmit,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": [
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/ai_tool.xml",
        "data/ai_tools.xml",
    ],
    "demo": [],
}
