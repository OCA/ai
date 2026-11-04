# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Message Import - Purchase",
    "summary": "Turn the received vendor quotes into draft purchase orders",
    "version": "17.0.1.0.0",
    "category": "Inventory/Purchase",
    "website": "https://github.com/OCA/ai",
    "author": "Binhex, Odoo Community Association (OCA)",
    "maintainers": ["oliverg09"],
    "license": "AGPL-3",
    "development_status": "Beta",
    "depends": ["ai_message_import", "purchase_stock"],
    "data": [
        "data/ai_message_import_prompt.xml",
        "views/ai_message_import_views.xml",
        "views/purchase_order_views.xml",
    ],
    "installable": True,
}
