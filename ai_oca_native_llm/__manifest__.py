# Copyright 2025 Pierre Verkest
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)
{
    "name": "Native AI LLM Integration (Ollama)",
    "version": "19.0.1.0.0",
    "category": "AI",
    "summary": "Core LLM wrapper for Ollama",
    "author": "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "LGPL-3",
    "depends": ["base"],
    "external_dependencies": {
        "python": ["ollama"],
    },
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
}
