# Copyright 2025 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA Bridge Extra Parameters",
    "summary": """Adds extra parameters to the AI OCA Bridge payload.""",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Binhex,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "category": "AI",
    "development_status": "Beta",
    "depends": ["ai_oca_bridge"],
    "data": [
        "security/ir.model.access.csv",
        "views/ai_bridge.xml",
        "views/ai_extra_parameter.xml",
        "views/menu.xml",
    ],
    "maintainers": ["arielbarreiros96"],
}
