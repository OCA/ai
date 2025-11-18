# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA Bridge Field Service",
    "summary": """Integrate AI Bridge with Field Service""",
    "version": "16.0.2.0.0",
    "license": "AGPL-3",
    "author": "Escodoo,Odoo Community Association (OCA)",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/OCA/ai",
    "depends": ["ai_oca_bridge", "fieldservice"],
    "data": [],
    "demo": [
        "demo/ai_bridge_demo.xml",
    ],
    "test": [
        "tests/test_fsm_order_ai_bridge.py",
    ],
}
