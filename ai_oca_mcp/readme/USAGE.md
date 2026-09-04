- Access in Developer mode
- Go to `AI > MCP Server`
- Create a new MCP Server and add the `generic` tools you want to expose
- Click **Add Key** to generate a new API key for a client — the key is only shown once
- Use the provided URL and the generated key to configure your AI client

## Connecting from n8n
Use the MCP node with:
- **URL**: the value shown in the `URL` field
- **Authentication**: Bearer Token
- **Token**: the generated API key

## Tool limitations
Only tools of kind `generic` are supported. Tools requiring a record context 
(`generic_model`, `record`) cannot be used via MCP.

## Security
Each client should have its own API key. Keys can be expired individually 
from the server form or from `AI > MCP Server Log` to audit all calls.
