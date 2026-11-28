# Copyright 2026 Coopdevs
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Tool Confirm",
    "summary": "Ask a human to confirm AI tool calls that modify data",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Coopdevs,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "maintainers": ["QuiJoQuim"],
    "depends": [
        "ai_tool",
        "base_setup",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/ai_tool_request_security.xml",
        "data/mail_activity_type_data.xml",
        "data/ir_cron_data.xml",
        "views/ai_tool_views.xml",
        "views/ai_tool_request_views.xml",
        "views/res_config_settings_views.xml",
    ],
}
