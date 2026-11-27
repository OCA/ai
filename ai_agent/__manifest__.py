# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Agent",
    "summary": """AI agent backed by a user, chatting through mail.message.""",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "SDi,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": [
        "ai_connection",
        "ai_tool_skill",
    ],
    "external_dependencies": {"python": ["markdown"]},
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/ir_cron.xml",
        "views/ai_agent.xml",
        "views/ai_agent_session.xml",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_agent/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "ai_agent/static/tests/*.js",
        ],
        "web.assets_tests": [
            "ai_agent/static/tests/tours/**/*",
        ],
    },
    "demo": [],
}
