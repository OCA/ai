# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Server Action",
    "summary": (
        "Integrate AI connections with server actions " "to automate tasks using LLMs."
    ),
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Dixmit,SDi,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": ["ai_connection", "ai_tool", "mail"],
    "external_dependencies": {
        "python": ["markdown"],
    },
    "data": [
        "views/ir_actions_server.xml",
    ],
    "demo": [],
}
