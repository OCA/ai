# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Field Vector Fill",
    "summary": """Autogenerate vectors and add search functions""",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Dixmit,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": [
        "field_vector",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/ir_model_field_vector.xml",
    ],
    "demo": [],
}
