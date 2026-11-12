This module lets MCP clients such as Claude connect to an `ai_oca_mcp` server
through an OAuth sign-in, instead of a key entered by hand.

When the user clicks **Connect** (or **Authenticate**) in the client, a browser
opens on Odoo. The user signs in, reviews the server, its tools and where the
client will return to, and clicks **Allow**. The client then receives a key
and uses it like any key created with **Add Key**.

Only internal users of the **Connect AI Clients with OAuth** group can allow
the access. The key belongs to the user who allowed it, so the tools run with
that user's access rights. It appears in the server's keys and can be expired
there to disconnect the client, and the user can disconnect it in their
preferences. It also stops working when the user is archived
or removed from the group, and expires when OAuth is turned off on the server
or this module is uninstalled.

The module implements the parts of the
[MCP authorization specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
that Claude needs: the authorization code flow with PKCE (S256), protected
resource and authorization server metadata, and dynamic client registration.
