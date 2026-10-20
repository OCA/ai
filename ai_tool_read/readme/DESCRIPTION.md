Adds `ai_tool` tools to let an AI agent read any model and field it
is allowed to access, while keeping personal or otherwise sensitive fields out
of the results.

A flag **AI Read Forbidden** (`ai_no_read`) is added to fields. The tools never
return nor describe a forbidden field, nor any field exposing its value:
related fields, including those delegated through `_inherits`, and computed
fields depending on it. Flagging `res.partner.email` thus also hides
`email_formatted`, `email_normalized` and `res.users.email`.

Three tools are provided:

- **list_models**: lists the models the current user is allowed to read.
- **get_fields**: describes a model's readable fields (label, type, help,
  selection options and relation target), and lists the forbidden ones under
  `hidden`.
- **search_read**: searches and reads records of a model. It returns the
  stored fields unless a field list is given, relational fields as record
  IDs, and dates in UTC. Results are paged with `limit` and `offset`, and
  `has_more` tells whether more records match. A field whose computation is
  refused for the user is left out and listed in `inaccessible_fields`, and a
  record the search finds but the user cannot read (as `ir.attachment` allows)
  is left out without notice, as record rules would.

The tools run with the calling user's own access rights (no `sudo`), so Odoo
ACLs, record rules and field `groups` still apply. Connect the agent as a user
with no more rights than it needs: an administrator sees every field restricted
by `groups`.

Besides forbidden fields, the results leave out binary fields, fields pointing
to a model the user cannot read (reading them would fail), and display names
computed on the fly, including the one Odoo adds to many2one values: they are
built from other records' fields, which may be forbidden there.

The flag keeps values out of the results, not out of searches: see *Known
issues*.
