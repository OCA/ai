# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Document Extraction",
    "summary": "Extract invoice data from PDFs and images using a vision LLM",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "website": "https://github.com/OCA/ai",
    "author": "VSL, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "development_status": "Alpha",
    "application": False,
    "installable": True,
    "depends": ["base", "account", "bus", "queue_job", "ai_connection"],
    "external_dependencies": {
        "python": ["Pillow", "pdf2image", "rapidfuzz", "requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/account_move_views.xml",
        "views/res_config_settings_views.xml",
        "views/ai_connection_views.xml",
        "wizards/extraction_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_document_extraction/static/src/account_move_form_ai_extraction.js",
        ],
    },
    "demo": [],
}
