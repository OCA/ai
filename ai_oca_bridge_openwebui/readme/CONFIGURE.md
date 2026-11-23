## OpenWebUI

1. Create an API key in *Settings → Account → API keys*.
2. Give the API-key user access to the selected model and any tools required
   by the bridge.
3. Configure prompts, knowledge bases, web search and tools in OpenWebUI.
   OpenWebUI remains the source of truth for those features.

## Odoo

1. Go to *AI Bridge → AI Bridge* and create or open a bridge.
2. Select **OpenWebUI Chat** as the payload type. The module enforces:
   * Chatter usage;
   * Immediate result kind;
   * Post a Message result type.
3. Set the OpenWebUI URL, for example:
   `https://<openwebui>/api/chat/completions`.
4. Select **Token Authentication** and enter the API key.
5. Synchronize the OpenWebUI catalog if desired, then select a model. A
   manually entered model identifier is also supported.
6. Configure the history size, timeout, optional system prompt, web search and
   tools.
7. Create or use an internal Odoo AI user and assign the bridge to its
   **AI Bridge** field.
8. Add the AI user to a Discuss conversation or channel. For a task, note or
   another `mail.thread` record, mention the AI user in the chatter.

The optional `Model` field restricts the bridge to one Odoo model. Leave it
empty to allow the same bridge to handle Discuss, tasks, notes and other
eligible chatter records.

## Context and history

`History Size` applies to every supported chatter model. The bridge also sends
the current record identity, description when available, creation/modification
dates, and dated chatter entries with their authors.

OpenWebUI-specific telemetry, cost trackers and custom filters are not part of
this OCA module. Configure those independently in OpenWebUI if needed.
