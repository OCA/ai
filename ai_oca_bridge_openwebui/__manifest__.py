# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA Bridge OpenWebUI",
    "summary": "Use OpenWebUI models and external tools in OCA chatter bridges",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Sébastien Couratin, Semper Connect, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "category": "AI",
    "development_status": "Alpha",
    "depends": [
        "ai_oca_bridge",
        "ai_oca_bridge_chatter",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/ai_bridge.xml",
    ],
    "installable": True,
}
