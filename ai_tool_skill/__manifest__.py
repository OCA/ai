# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Tool Skill",
    "summary": "Manages AI skills and generates dynamic "
    "AI tools for each skill instance.",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "SDi,Odoo Community Association (OCA)",
    "maintainers": ["angelmoya"],
    "contributors": [
        "Ángel Moya <amoya@sdi.es>",
    ],
    "website": "https://github.com/OCA/ai",
    "depends": [
        "ai_tool",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/ai_skill_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
}
