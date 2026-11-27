Bridge module connecting ``ai_oca_native_llm`` and ``ai_tool``.

Converts Odoo ``ai.tool`` definitions into OpenAI function tool schemas and System 1
Decision candidate choices, and lets ``ai.llm.client`` accept ``ai.tool`` recordsets
directly in ``chat()`` and ``decide_tool()``.
