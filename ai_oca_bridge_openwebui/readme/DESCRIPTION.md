This module connects an Odoo AI user to OpenWebUI through OpenWebUI's
server-side chat flow.

It extends the OCA modules `ai_oca_bridge` and `ai_oca_bridge_chatter` with an
**OpenWebUI Chat** bridge payload.

The integration deliberately separates responsibilities:

- Odoo manages users, access rights, Discuss channels, mentions, Odoo records,
  chatter history and the final answer posted back to the originating record.
- OpenWebUI manages model execution, prompts, web search, tools, knowledge
  bases, sources and provider-specific reasoning output.

The bridge supports any eligible `mail.thread` record, including Discuss
channels, conversations, tasks and notes. It sends a bounded, enriched context
containing the current record identity and dated chatter history, then posts the
final assistant answer back to the same Odoo record.

The Odoo module is a transport and context adapter.
