# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Tool Server Action",
    "summary": "Allow configuring AI Tools using Server Actions",
    "version": "18.0.1.0.0",
    "category": "Hidden",
    "author": "SDi, Odoo Community Association (OCA)",
    "maintainers": ["amoya@sdi.es"],
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": [
        "ai_tool",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/ai_tool_server_action_wizard_views.xml",
        "views/ai_tool_views.xml",
        "views/ir_actions_server_views.xml",
    ],
    "installable": True,
}
