- Refresh tokens are not issued. When a key expires, the user connects again.
- Client registrations are not stored: the redirect URI allow-list, PKCE and the
  user's approval protect the flow.
- Client ID Metadata Documents are not supported. Claude falls back to dynamic
  client registration.
- When `auth_oauth_server`
  ([OCA/server-auth#1032](https://github.com/OCA/server-auth/pull/1032)) is
  available, this module could rely on it for the authorization server and keep
  only the link with the MCP servers.
