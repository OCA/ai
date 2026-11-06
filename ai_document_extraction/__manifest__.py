# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Document Extraction",
    "summary": "Extract invoice data from PDFs and images using an AI connection",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "website": "https://github.com/OCA/ai",
    "author": "VSL, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "development_status": "Alpha",
    "depends": ["account", "ai_connection"],
    "external_dependencies": {
        "python": ["Pillow", "pdf2image", "rapidfuzz"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/extraction_wizard_views.xml",
    ],
    "demo": [],
}
