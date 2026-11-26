# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA Bridge OpenWebUI",
    "summary": "OpenWebUI provider and shared OCA AI Bridge configuration",
    "version": "18.0.3.0.0",
    "license": "AGPL-3",
    "author": "Sébastien Couratin, Semper Connect, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "category": "AI",
    "development_status": "Alpha",
    "depends": ["ai_oca_bridge"],
    "data": [
        "security/ir.model.access.csv",
        "views/ai_bridge.xml",
    ],
    "installable": True,
}
