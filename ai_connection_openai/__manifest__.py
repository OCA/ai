# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Ai Automation Openai",
    "summary": """Integrate automation with OpenAI/LiteVLLM Api""",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Dixmit,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": [
        "ai_connection",
    ],
    "data": [
        "views/ai_connection.xml",
    ],
    "demo": [],
    "external_dependencies": {
        "python": [
            "openai",
        ],
    },
}
