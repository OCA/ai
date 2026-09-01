# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Tool Sale CRM",
    "summary": "AI Tools exposing Sales and CRM business actions",
    "version": "19.0.1.0.0",
    "category": "Services/AI",
    "author": "Pierre Verkest, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": [
        "ai_tool",
        "crm",
        "sale_crm",
    ],
    "data": [
        "data/ai_tools_sale_crm.xml",
    ],
    "installable": True,
    "application": False,
}
