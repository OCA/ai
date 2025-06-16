# Copyright 202 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Ai Oca Bridge Chatter",
    "summary": """Integrate a Bridge with a user that will use it on chatter""",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Dixmit,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "depends": [
        "ai_oca_bridge",
    ],
    "data": [
        "views/res_users.xml",
        "views/ai_bridge.xml",
    ],
    "demo": [],
}
