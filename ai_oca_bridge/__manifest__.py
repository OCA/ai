# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA Bridge",
    "summary": """Makes a basic configuration to be used as bridge with external AI systems""",
    "version": "16.0.2.0.1",
    "license": "AGPL-3",
    "author": "Dixmit,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "category": "AI",
    "development_status": "Beta",
    "depends": ["mail"],
    "data": [
        "data/ir_module_category.xml",
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/menu.xml",
        "views/ai_bridge_execution.xml",
        "views/ai_bridge.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_oca_bridge/static/src/**/*.xml",
            "ai_oca_bridge/static/src/**/*.esm.js",
        ],
        "web.qunit_suite_tests": [
            "ai_oca_bridge/static/tests/web/**/*.esm.js",
        ],
        "web.tests_assets": [
            "ai_oca_bridge/static/tests/helpers/**/*.esm.js",
        ],
    },
    "application": True,
}
