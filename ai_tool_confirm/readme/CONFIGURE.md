In *Settings > General Settings > AI*:

- **AI confirmation expiration**: hours a pending request waits for an answer
  before it expires (24 by default, 0 for never).
- **AI confirmation limit**: pending requests a user can receive in an hour (20
  by default, 0 for no limit). Beyond it, new requests are refused and the AI is
  told so: nobody gets flooded with requests, which would end up approved
  without being read.
- **AI confirmation fallback approver**: user who confirms the requests with no
  person behind (scheduled actions, job queues, webhooks) on records without a
  responsible user. Avoid an administrator here: approved actions run with the
  approver's rights, and these requests may come from automations fed by
  external input (incoming emails, documents) that an attacker could use to
  steer the AI.

In *Settings > Technical > AI > AI Tool*, the **Human Confirmation** field of
each tool decides when it must be confirmed:

- *When the tool modifies data* (default): every tool not flagged as read-only.
- *Always* / *Never*: overrides the read-only flag of the tool.
