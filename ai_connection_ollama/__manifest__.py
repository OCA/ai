# Copyright 2026 SDi - Angel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Connection Ollama",
    "summary": """Ollama provider for AI connections""",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "SDi,Odoo Community Association (OCA)",
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
            "ollama",
        ],
    },
}
