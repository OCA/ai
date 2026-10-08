# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Tool - Read",
    "summary": "Generic ai_tool to read any model/field, with a per-field opt-out flag",
    "version": "19.0.1.0.0",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "author": "Quartile,Odoo Community Association (OCA)",
    "maintainers": ["nobuQuartile"],
    "depends": [
        "ai_tool",
    ],
    "data": [
        "views/ir_model_fields_views.xml",
        "data/ai_tools.xml",
    ],
}
