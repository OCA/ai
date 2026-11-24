# Copyright 2026 Nimarosa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Connection Usage",
    "summary": "Log AI calls, compute their cost and cap the monthly spend",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Nimarosa,Odoo Community Association (OCA)",
    "maintainers": ["nimarosa"],
    "website": "https://github.com/OCA/ai",
    "category": "Productivity",
    "development_status": "Beta",
    "depends": [
        "ai_connection",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/ai_connection_usage_security.xml",
        "views/ai_connection_usage.xml",
        "views/ai_connection.xml",
        "views/res_company.xml",
    ],
    "installable": True,
}
