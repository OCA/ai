## Responsibilities

This module is a transport and integration layer. It does not implement a
knowledge base, RAG engine, agent framework or external-tool runtime in Odoo.
Those capabilities are configured and executed by OpenWebUI.

Odoo provides the conversation context from Discuss. The bridge can add an
optional local system prompt and the Odoo channel name, then sends the recent
conversation as `user` and `assistant` messages.

Requests use:

- `POST /api/chat/completions`;
- `stream: false`;
- the configured model identifier;
- optional OpenWebUI tool identifiers.

The current implementation expects a response of the form:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Answer"
      }
    }
  ]
}
```

A failed request or an empty answer is recorded as an error in the bridge
execution and is not posted to Discuss.

## Catalog synchronization

The optional synchronization uses:

- `GET /api/models`;
- `GET /api/v1/tools/`.

Odoo stores only the identifiers, names and tool descriptions needed for
configuration. OpenWebUI remains the authoritative system for model behavior,
knowledge bases and tools.
