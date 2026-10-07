Base infrastructure for defining **AI tools** in Odoo: a registry that turns
decorated Odoo methods into structured, schema-described functions that AI
clients can list and invoke.

A tool is defined by:

- an `ai.tool` record (name, description, target model and method), and
- an `@aitool`-decorated method declaring JSON input/output schemas.

Three tool kinds describe how the method is invoked:

- `generic` — called on the model class; no record context needed;
- `generic_model` — model-level call that still receives a `record` argument;
- `record` — called on a specific record of the model.

Tools are meant to be consumed by integration modules — e.g. `ai_oca_mcp`
exposes `generic` tools over the Model Context Protocol — or by automation
flows. Calls execute with the permissions of the calling user.

The module ships two demo tools: `get_date` (returns today's date) and
`post_message` (posts a message on a record).
