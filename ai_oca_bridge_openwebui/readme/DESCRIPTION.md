This module connects Odoo Discuss with [OpenWebUI](https://openwebui.com)
through its OpenAI-compatible chat completions API.

It extends the OCA modules `ai_oca_bridge` and `ai_oca_bridge_chatter` with an
**OpenWebUI Chat** bridge payload.

The integration deliberately separates responsibilities:

- Odoo remains responsible for users, access rights, Discuss channels, Odoo
  records and conversation history.
- OpenWebUI remains responsible for AI orchestration, models, system prompts,
  knowledge bases, RAG, agents and external tools.

The module sends the selected Discuss history to OpenWebUI and posts the
assistant response back as the configured Odoo AI user. The optional bridge
system prompt adds local Odoo context; it does not replace OpenWebUI's own
configuration.

The synchronized models and tools are only a local Odoo catalog used for
selection. OpenWebUI remains the source of truth for their behavior and
configuration.
