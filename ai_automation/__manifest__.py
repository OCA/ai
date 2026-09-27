# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Ai Automation",
    "summary": """
        Integrate `ai_tools` with server actions to automate tasks using AI.
    """,
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Dixmit,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": ["ai_tool"],
    "external_dependencies": {
        "python": ["ollama"],
    },
    "data": [
        "views/ir_actions_server.xml",
        "security/ir.model.access.csv",
        "views/ai_connection.xml",
    ],
    "demo": [],
}
