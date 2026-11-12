# Copyright 2025 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Native AI LLM Integration",
    "version": "19.0.1.0.0",
    "category": "AI",
    "summary": "Core LLM wrapper using OpenAI client",
    "author": "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": ["base", "ai_oca_native_base"],
    "external_dependencies": {
        "python": ["openai"],
    },
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
}
