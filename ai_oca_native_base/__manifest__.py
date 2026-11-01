# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Native Base",
    "summary": "Base AI configuration root menu & security groups",
    "version": "19.0.1.0.0",
    "category": "Services/AI",
    "author": "Pierre Verkest, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": [
        "base",
    ],
    "data": [
        "security/ai_security.xml",
        "views/ai_menus.xml",
    ],
    "installable": True,
    "application": False,
}
