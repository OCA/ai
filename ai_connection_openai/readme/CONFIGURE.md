Create an AI Connection of kind OpenAI and fill the model, the URL of the
OpenAI-compatible endpoint and the key.

The key can be stored in the connection (API Key) or kept out of the database:
fill API Key Environment Variable with the name of an environment variable of
the Odoo server that holds it. When that name is set, the key is read from the
environment on every call, the stored key is ignored, and a call fails with a
clear message if the variable is missing.

Which variables may be used, and where their keys may be sent, is decided by
the server, not by the database: the Odoo configuration file must list them in
the `ai_connection_openai_env_allowlist` option, comma separated. Each entry is
an exact name or a prefix ending with `*`, optionally pinned to the only host
the key may be sent to with `@host`:

```ini
[options]
ai_connection_openai_env_allowlist = OPENAI_API_KEY@api.openai.com,AI_KEY_*@llm.example.com
```

With a host, the key is only used when the connection URL is `https` and its
host is exactly that one (no user information in the URL). Without a host the
key may be sent to any `https` URL, and every call logs a warning saying so. A
bare `*` is ignored. Without the option no variable is allowed: otherwise an
administrator of any database served by the instance could read any variable
of the server process (database password, master password...) by sending it
to an URL of their own.
