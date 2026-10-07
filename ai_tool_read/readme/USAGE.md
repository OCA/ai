The tools are registered as `ai.tool` records and are callable through any
`ai_tool` integration: `ai_oca_mcp`, for instance, exposes them to MCP clients
such as Claude Desktop. This module provides the tools themselves; how they are
reached depends on the transport module installed.

A typical agent workflow:

1. Call `list_models` to discover the models the bound user may read. Each
   entry gives the technical `model` name (e.g. `res.partner`) to pass to the
   other tools.
2. Call `get_fields` with `model` to learn what each readable field means
   (label, type, help, selection options, relation target), and which fields
   are listed under `hidden`.
3. Call `search_read` to fetch records:

   - `model` (required): the technical model name.
   - `domain` (optional): an Odoo domain as a list, e.g.
     `[["is_company", "=", true]]`.
   - `fields` (optional): an explicit field list; the stored readable fields
     are returned otherwise. An empty list returns ids only.
   - `limit` (optional): page size, 200 by default and at most; a value of 0
     or less, or past the cap, is treated as the maximum.
   - `offset` (optional): skip that many matching records.
   - `order` (optional): e.g. `"name asc"`.

   Relational fields come back as record ids, dates and datetimes as ISO-8601
   strings in UTC. `has_more` tells whether another page exists under the same
   domain and order; fields the call could not read are listed in
   `inaccessible_fields`, while forbidden or restricted fields are simply
   absent from the records.

Example `search_read` arguments:

```json
{
  "model": "res.partner",
  "domain": [["is_company", "=", true]],
  "fields": ["name", "email", "country_id"],
  "limit": 20,
  "order": "name asc"
}
```

Every call executes with the access rights of the calling user — the API-key
owner when reached through `ai_oca_mcp` — so Odoo ACLs, record rules and field
`groups` apply as usual. Connect the agent as a dedicated user holding only
the rights it needs.
