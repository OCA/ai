- Approval by any member of a group, for requests no person asked for (e.g.
  contacts created from incoming emails), instead of a single approver.
- Approve or reject several requests at once from the list, keeping every
  check of a single answer.
- An optional "Approver" policy per tool (requesting user, record responsible,
  group), set by the administrator.
- The audit trail only covers documents with a chatter (`mail.thread`): lines
  and technical records created or modified by an approved action are not
  listed.
- Argument names are resolved to record names only when a model of the call has
  a relational field with the same name: other ids are shown as they are, unless
  the tool describes its calls with a `_describe` method.
- `_describe` methods must only read data, but this is not enforced: rolling
  back a savepoint would also drop the pending tracking of the transaction.
