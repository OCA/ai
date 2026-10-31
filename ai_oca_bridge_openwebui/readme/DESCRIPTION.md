This module connects an Odoo Discuss AI user to an OpenWebUI user through
OpenWebUI's server-side agentic chat flow.

It extends the OCA modules `ai_oca_bridge` and `ai_oca_bridge_chatter` with an
**OpenWebUI Chat** bridge payload.

The integration deliberately separates responsibilities:

- Odoo manages users, access rights, Discuss channels, mentions, Odoo records
  and the final answer posted back to Discuss.
- OpenWebUI manages model execution, prompts, web search, tools, knowledge
  bases, sources and provider-specific reasoning output.

The bridge creates an OpenWebUI conversation using the Odoo Discuss channel
name, keeps the original user question visible, submits an agentic streaming
request, waits for server-side tools such as web search to finish, and posts
the final assistant answer back to Discuss.

The OpenWebUI conversation can be retained for review by the OpenWebUI user.
When retained, it can expose the original question, the assistant answer, web
search activity, sources and model/provider reasoning information when those
features are supported and enabled by OpenWebUI. Hidden chain-of-thought is
not guaranteed to be exposed.

The Odoo bridge does not execute OpenWebUI tool calls itself. OpenWebUI remains
the authoritative runtime for web search, tools, knowledge bases and sources.
