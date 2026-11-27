# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Agent Salesman",
    "summary": "Specialized AI Sales Agent configuration with CRM/Sales tools",
    "version": "19.0.1.0.0",
    "category": "Services/AI",
    "author": "Pierre Verkest, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": [
        "ai_oca_native_agent_tool",
        "ai_tool_sale_crm",
        "sales_team",
    ],
    "data": [
        "data/ai_agent_salesman_data.xml",
    ],
    "installable": True,
    "application": False,
}
