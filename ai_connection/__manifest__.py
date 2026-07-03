# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Ai Connection",
    "summary": """Creates connections to AI systems""",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Dixmit, SDi, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": [
        "ai_tool",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
        "wizards/ai_connection_run_wizard_views.xml",
        "views/ai_connection.xml",
        "views/ai_connection_execution.xml",
    ],
    "demo": [],
}
