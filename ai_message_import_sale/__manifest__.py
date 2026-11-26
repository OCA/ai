# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Message Import - Sale",
    "summary": "Turn the received customer orders into draft sales quotations",
    "version": "18.0.1.0.0",
    "category": "Sales/Sales",
    "website": "https://github.com/OCA/ai",
    "author": "Binhex, Odoo Community Association (OCA)",
    "maintainers": ["oliverg09"],
    "license": "AGPL-3",
    "development_status": "Beta",
    "depends": ["ai_message_import", "sale_stock"],
    "data": [
        "data/ai_message_import_prompt.xml",
        "views/ai_message_import_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
}
