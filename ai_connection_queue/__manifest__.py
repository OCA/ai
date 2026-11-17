# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Ai Connection Queue",
    "summary": """Run ai.connection conversations through queue_job""",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "SDi,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": [
        "ai_connection",
        "queue_job",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "demo": [],
}
