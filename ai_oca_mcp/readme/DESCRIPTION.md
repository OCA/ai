Expose Odoo as an MCP (Model Context Protocol) server, allowing external AI
clients — such as n8n, custom agents, or any MCP-compatible tool — to invoke
Odoo functions through the standardized MCP protocol.

Each MCP server publishes a set of **AI tools** (defined by the `ai_tool`
module). Clients exchange JSON-RPC 2.0 messages with Odoo over HTTP POST:
`tools/list` returns the tool catalogue and `tools/call` executes a tool.

Key characteristics:

- **Authentication**: per-client API keys sent as Bearer tokens. Keys are stored
  hashed and are shown only once, at creation.
- **Per-user permissions**: every key is bound to an Odoo user and calls execute
  with that user's permissions — a client can only do what its key's user can
  do.
- **Key lifecycle**: keys can carry an expiration date or be expired manually at
  any time.
- **Audit log**: every tool invocation is recorded with its parameters and
  result or error.

Notes:

- Transport is plain JSON-RPC over HTTP POST. SSE/streaming transports and
  notifications are not supported.
- Claude Desktop requires OAuth 2.0 authorization. Odoo does not act as an
  OAuth authorization server, so clients that mandate OAuth need an extension
  (for example, validating externally-issued tokens via `auth_jwt` from
  OCA/server-auth).
