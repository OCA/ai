# Copyright 2025 Pierre Verkest
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)
{
    "name": "Native AI Thread (Chatter UI)",
    "version": "19.0.1.0.0",
    "category": "AI",
    "summary": "AI Thread history and Chatter UI integration",
    "author": "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "LGPL-3",
    "depends": ["mail", "ai_oca_native_llm"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/ai_thread_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_oca_native_thread/static/src/components/**/*",
        ],
        "web.assets_tests": [
            "ai_oca_native_thread/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
