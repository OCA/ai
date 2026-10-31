## Responsibilities

This module connects an Odoo Discuss AI user to an OpenWebUI user through the
OpenWebUI server-side agentic chat flow.

Odoo remains responsible for:

- Odoo users and access rights;
- Discuss channels and mentions;
- Odoo records and internal conversation history;
- posting the final assistant answer back to Discuss.

OpenWebUI remains responsible for:

- model execution and system prompts;
- Native Function Calling / Agentic Mode;
- web search and web loaders;
- knowledge bases and RAG;
- tools, sources and provider-specific reasoning output.

## Agentic OpenWebUI flow

For an OpenWebUI bridge, Odoo:

1. prepares the Discuss history and the current user question;
2. creates an OpenWebUI conversation whose title is the Odoo Discuss channel
   name;
3. creates the user and assistant message tree, keeping the original question
   visible in OpenWebUI;
4. submits a streaming request with `chat_id`, assistant `id`, `session_id`
   and the configured built-in features;
5. waits for OpenWebUI's server-side tool loop to finish;
6. reads the final assistant message from the OpenWebUI conversation;
7. posts the final answer to the Odoo Discuss channel;
8. keeps or deletes the OpenWebUI conversation according to
   **Keep OpenWebUI Conversation**.

The server-side OpenWebUI flow is required for built-in tools such as web
search. Odoo does not execute OpenWebUI tool calls itself.

## Web search

When **Enable Web Search** is checked, the bridge sends the OpenWebUI feature
flag:

```json
{
  "features": {
    "web_search": true
  }
}
```

OpenWebUI then performs the search with the API-key user's permissions and
returns the final answer and, where supported, sources and tool activity.

A successful web-search request requires a configured OpenWebUI search engine,
valid credentials, user permission and a model supporting Native Function
Calling / Agentic Mode.

## OpenWebUI conversation visibility

When **Keep OpenWebUI Conversation** is enabled, the conversation remains in
OpenWebUI. The OpenWebUI user can review:

- the original Odoo user question;
- the assistant response;
- web-search activity and sources when provided by OpenWebUI;
- tool calls and other structured output exposed by the selected model;
- provider/model reasoning information when the model and OpenWebUI expose it.

Reasoning visibility is provider- and model-dependent. The module does not
promise that hidden chain-of-thought will be exposed; it only preserves the
OpenWebUI conversation and structured information returned by OpenWebUI.

When the option is disabled, the temporary conversation is deleted after the
final response or after an error, when possible.

## Internal Odoo references

Odoo record references such as `/odoo/res.partner/<id>` are internal context.
They are not sources and must not be presented as sources by the assistant.

## Catalog synchronization

The optional synchronization uses:

- `GET /api/models`;
- `GET /api/v1/tools/`.

Odoo stores only the identifiers, names and descriptions needed for bridge
configuration. OpenWebUI remains authoritative for model behavior, tool
execution, web search and sources.

## Errors and timeouts

A failed request, timeout or empty final answer is recorded as an error on the
bridge execution and is not posted to Discuss. The timeout applies to the
OpenWebUI HTTP requests and to the server-side agentic task polling.
