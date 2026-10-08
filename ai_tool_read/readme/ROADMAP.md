The tools keep forbidden values out of their results, not out of the searches
an agent runs: they are not meant to stop an agent that probes for hidden
values on purpose. Each case below still lets a forbidden value through:

- **Filtering on a forbidden field.** `[("email", "ilike", "@example.com")]`
  lists the contacts whose address matches, and repeating it on longer
  fragments rebuilds a whole address. The same works on fields restricted by
  `groups=`, which Odoo does not check when searching, and on search-only
  fields: `phone_mobile_search` rebuilds a phone number even when `phone` is
  forbidden.
- **Searching a relation by text.** `[("partner_id", "ilike", "@example.com")]`
  searches contacts by name, email included, and finds the orders of the
  contacts whose address matches.
- **Sorting.** Ordering on a forbidden field, or on a many2one (sorted by the
  related record's display name), reveals the order of the hidden values.
- **Copied values.** A value copied into another record is not linked to its
  source: the author's address in a chatter message
  (`mail.message.email_from`) is returned unless that field is flagged too.

One more limit, which leaks nothing: a requested field that is forbidden,
binary or restricted is simply missing from the records, with no reason given;
`get_fields` tells them apart.
