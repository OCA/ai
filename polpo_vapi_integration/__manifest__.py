{
    "name": "Odoo Vapi Call Integration",
    "summary": "Integrate Odoo with Vapi.ai for voice agent call logging and management.",
    "description": "This module enables seamless integration between Odoo and Vapi.ai, allowing automated logging and management of calls handled by AI voice agents. It provides call logs, settings, and user-specific API keys.",
    "version": "16.0.1.0.0",
    "author": "Odoo Community Association (OCA)",
    "maintainers": ["qappsuy"],
    "website": "https://github.com/OCA/server-tools",
    "category": "Extra Tools",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "icon": "/polpo_vapi_integration/static/description/icon.png",
    "data": [
        "security/ir.model.access.csv",
        "views/vapi_integration_vapi_sdk.xml",
        "views/vapi_log_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "/polpo_vapi_integration/static/src/js/vapi_integration_widget.js",
        ],
    },
    "installable": True,
    "application": False,
}