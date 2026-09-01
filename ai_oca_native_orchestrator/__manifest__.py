# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI Native Orchestrator",
    "summary": "Agent Orchestrator engine & task thread dispatching",
    "version": "19.0.1.0.0",
    "category": "Services/AI",
    "author": "Pierre Verkest, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/ai",
    "license": "AGPL-3",
    "depends": [
        "ai_oca_native_thread",
        "ai_oca_native_llm",
        "ai_oca_native_agent",
        "ai_oca_native_agent_tool",
    ],
    "data": [
        "data/ai_prompt_data.xml",
    ],
    "installable": True,
    "application": False,
}
