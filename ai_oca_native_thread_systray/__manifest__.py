# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Native AI Thread Systray Notification",
    "version": "19.0.1.0.0",
    "category": "AI",
    "summary": "AI Thread real-time top-bar Systray task tracking and navigation",
    "author": "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": [
        "mail",
        "ai_oca_native_thread",
    ],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "ai_oca_native_thread_systray/static/src/components/systray/**/*",
        ],
        "web.assets_tests": [
            "ai_oca_native_thread_systray/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
