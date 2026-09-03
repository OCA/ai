# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Native Agent",
    "summary": "AI Agent model, Personas, System Prompts & User Context Security",
    "version": "19.0.1.0.0",
    "category": "Services/AI",
    "author": "Pierre Verkest, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": [
        "base",
        "mail",
        "ai_oca_native_base",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/ai_prompt_template_views.xml",
        "views/ai_persona_views.xml",
        "views/ai_agent_views.xml",
    ],
    "installable": True,
    "application": False,
}
