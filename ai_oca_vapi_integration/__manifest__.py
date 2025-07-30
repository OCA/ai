{
    "name": "Odoo Vapi Call Integration",
    "summary": "Integrate Odoo with Vapi.ai for voice agent call logging and management.",
    "version": "16.0.1.0.0",
    "author": "Odoo Community Association (OCA)",
    "maintainers": ["qappsuy"],
    "website": "https://github.com/OCA/ai",
    "category": "Extra Tools",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "icon": "/ai_oca_vapi_integration/static/description/icon.png",
    "data": [
        "security/ir.model.access.csv",
        "views/vapi_log_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        "views/vapi_integration_vapi_sdk.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "/ai_oca_vapi_integration/static/src/js/vapi_integration_widget.js",
        ],
        "web.assets_frontend": [
            "ai_oca_vapi_integration/static/src/js/vapi_sdk.js",
        ],
    },
    "installable": True,
    "application": False,
}
