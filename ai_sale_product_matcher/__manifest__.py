# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Sale Product Matcher",
    "summary": "Find best-matched PIM products from requirement docs/images using AI",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "website": "https://github.com/OCA/ai",
    "author": "VSL, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "development_status": "Alpha",
    "application": False,
    "installable": True,
    "depends": [
        "sale",
        "product",
        "bus",
        "queue_job",
        "ai_connection",
        "ai_tool",
    ],
    "external_dependencies": {
        "python": ["Pillow", "pdf2image", "rapidfuzz", "requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "wizards/requirement_wizard_views.xml",
        "views/sale_order_views.xml",
        "views/ai_product_match_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_sale_product_matcher/static/src/sale_order_ai_matcher.js",
        ],
    },
    "demo": [],
}
