- Open the MCP server in `AI > MCP Server` and check **OAuth**.
- Add the users who may connect AI clients to the group **Connect AI Clients
  with OAuth** (`Settings > Users & Companies > Groups`, in developer mode).
- Make sure the `web.base.url` system parameter is the URL clients use to reach
  Odoo (set `web.base.url.freeze` to `True` behind a reverse proxy). The
  server's **URL** must match the URL entered in the client exactly.

Optional system parameters:

- `ai_oca_mcp_oauth.redirect_uris`: the redirect URIs of other MCP clients to
  allow, separated by spaces or new lines, for example
  `https://chatgpt.com/connector_platform_oauth_redirect` for ChatGPT. Claude and
  Claude Code are always allowed. For `localhost` and `127.0.0.1`, any port is
  accepted, but the path must match.
- `ai_oca_mcp_oauth.token_lifetime_days`: how many days an issued key is valid
  (default `30`). When it expires, the client asks the user to connect again.
