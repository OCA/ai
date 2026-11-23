## Responsibilities

This module connects an Odoo AI user to OpenWebUI through OpenWebUI's
server-side chat flow.

Odoo remains responsible for:

- users and access rights;
- Discuss channels and mentions;
- any `mail.thread` record, including tasks and notes;
- local record and chatter context;
- posting the final assistant answer back to the originating record.

OpenWebUI remains responsible for:

- model execution and system prompts;
- web search and agentic tools;
- knowledge bases and RAG;
- provider-specific reasoning and sources.

## Request flow

For each eligible chatter message, Odoo:

1. identifies the originating `mail.message` and its target model/record;
2. builds a bounded history of previous chatter comments;
3. adds explicit record identity, description, dates, authors and message IDs;
4. creates an OpenWebUI conversation and submits the server-side chat request;
5. waits for the final assistant message;
6. posts the answer back to the originating Discuss channel, task or other
   supported `mail.thread` record.

`History Size` applies to all supported chatter records, not only Discuss.
It limits the number of previous user exchanges included in the request.

The bridge does not execute OpenWebUI tools in Odoo. OpenWebUI remains the
runtime for model execution and external tools.

## Context and references

The current Odoo record is the authoritative target. A mention such as
`/odoo/res.partner/<id>` is only a linked contact reference and must not be
mistaken for the task or record in which the assistant was called.

History entries include their Odoo message ID, date, author and content so the
assistant can answer questions about the latest note reliably.

## Conversation retention

When **Keep OpenWebUI Conversation** is enabled, the OpenWebUI conversation is
kept for review. When disabled, the temporary conversation is deleted after
processing when possible.

## Errors and timeouts

A failed request, timeout or empty answer is recorded on the bridge execution
and is not posted as an assistant answer.
