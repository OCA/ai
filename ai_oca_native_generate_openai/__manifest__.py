# Copyright 2026 Nitrokey GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI - Generate text using an OpenAI compatible server",
    "summary": """This module replaces AI from html_editor to use an OpenAI
compatible server instead of OpenAI through Odoo IAP.""",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Nitrokey GmbH,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": ["html_editor"],
    "external_dependencies": {"python": ["openai"]},
    "data": [],
    "demo": [],
}
