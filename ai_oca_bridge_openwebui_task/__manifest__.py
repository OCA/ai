# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA Bridge OpenWebUI Project Tasks",
    "summary": "Draft project task descriptions with a configured OpenWebUI bridge",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Sébastien Couratin, Semper Connect, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "category": "AI",
    "development_status": "Alpha",
    "depends": ["ai_oca_bridge_openwebui_discuss", "project"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/task_description_wizard_views.xml",
        "views/project_task_views.xml",
    ],
    "installable": True,
}
