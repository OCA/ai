# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Native Agent Tool Bridge",
    "summary": "Links AI Agents to allowed AI Tools and provides tool schemas",
    "version": "19.0.1.0.0",
    "category": "Services/AI",
    "author": "Pierre Verkest, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": [
        "ai_oca_native_agent",
        "ai_tool",
    ],
    "data": [
        "data/ai_tool_agent_discovery.xml",
        "views/ai_agent_views.xml",
    ],
    "installable": True,
    "application": False,
}
