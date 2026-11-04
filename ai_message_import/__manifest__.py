# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Message Import",
    "summary": "Turn the documents received by any channel into draft orders "
    "with an AI connection",
    "version": "17.0.1.0.0",
    "category": "Productivity",
    "website": "https://github.com/OCA/ai",
    "author": "Binhex, Odoo Community Association (OCA)",
    "maintainers": ["oliverg09"],
    "license": "AGPL-3",
    "development_status": "Beta",
    "depends": ["mail_message_import", "ai_connection", "account", "product"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "data/ir_sequence.xml",
        "data/ai_message_import_prompt.xml",
        "views/ai_message_import_document_views.xml",
        "views/ai_message_import_product_mapping_views.xml",
        "views/ai_message_import_partner_mapping_views.xml",
        "views/ai_message_import_uom_mapping_views.xml",
        "views/ai_message_import_change_views.xml",
        "views/ai_message_import_prompt_views.xml",
        "views/mail_message_import_config_views.xml",
        "views/mail_message_import_channel_views.xml",
        "views/mail_message_import_sender_views.xml",
        "views/mail_message_import_message_views.xml",
        "views/mail_message_import_conversation_views.xml",
        "views/mail_message_import_incident_views.xml",
        "wizards/ai_message_import_order_confirm_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_message_import/static/src/**/*",
        ],
    },
    "installable": True,
}
