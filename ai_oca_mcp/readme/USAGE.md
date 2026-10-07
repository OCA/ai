## Configure an MCP server

1. Activate developer mode and go to `Settings > Technical > AI > MCP Server`.
2. Create a server, give it a name, and select the `generic` tools you want to
   expose.
3. The `URL` field shows the client endpoint — it already includes the server's
   unique path key.

## Create a client key

1. Click **Add Key** on the server form.
2. Choose the user the client will act as and, optionally, an expiration date.
3. Copy the generated key — it is stored hashed and **shown only once**.

Configure your client with:

- **URL**: the server's `URL` field
- **Authentication**: Bearer token
- **Token**: the generated API key

### Connecting from n8n

Use the *MCP Client* node with:

- **Endpoint**: the server's `URL` field
- **Authentication**: Bearer Token
- **Token**: the generated API key
- **Transport**: HTTP — the endpoint expects POST requests; SSE is not supported

## Tool limitations

Only tools of kind `generic` are exposed. Tools requiring a record context
(`generic_model`, `record`) cannot be called via MCP.

`ai_tool` itself ships only demo tools (`get_date`, `post_message`), of which
just `get_date` is callable via MCP. Generic read access to Odoo data —
listing models, describing fields and `search_read` — is provided by the
`ai_tool_read` addon (proposed in OCA/ai#122), which also adds a per-field AI
opt-out for sensitive data. Other capabilities — creating documents,
triggering actions — come from extension modules that define their own
`@aitool`-decorated methods and `ai.tool` records (see the `ai_tool`
documentation). Whatever a tool can do is limited by the permissions of the
user bound to the API key.

Tools are not limited to reading data: a tool method runs real ORM code and can
also create or update records and call actions, always within the key owner's
permissions. Results must be JSON-serializable — return plain dicts and convert
dates, recordsets and binary values yourself — otherwise the call is logged and
returns a JSON-RPC error.

## Security and auditing

- Create one key per client, so a compromised client can be revoked without
  affecting the others.
- Calls execute with the key owner's permissions: prefer a dedicated user with
  minimal access rights to limit what clients can reach.
- Internal users can view their own keys and the related servers, but only
  administrators can create or modify servers and keys.
- Keys can be expired manually from the server form, or automatically once they
  reach their expiration date.
- `AI > MCP Server Log` records every tool invocation with its parameters and
  result or error — use it to audit client activity.
