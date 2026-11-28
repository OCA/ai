When an AI integration calls a tool that requires confirmation, the tool is not
executed. Instead:

1. An AI tool request is created. It freezes the call: the arguments, the
   record, the tool (function, model and kind) and the company. It also keeps
   the requester, the approver, the origin and the expiration date.
2. The caller (the LLM, the MCP client) receives a
   `{"status": "pending_confirmation", ...}` result instead of the tool
   output, so it can tell the user.
3. The approver gets a *Confirm AI Action* activity. From the request they
   can **Approve** it, and the tool runs with their access rights, or
   **Reject** it. Either way, the answer is logged on the chatter of the
   record of the request.
4. Every document (model with a chatter) created or modified by an approved
   action says so in its chatter: the AI proposes, the user disposes.

**Who approves.** Whoever executes the tool: the user it runs as or, when code
runs it as OdooBot within a web request, the user of that request. When no
person is behind (scheduled actions, job queues, webhooks), the responsible
user of the record (its `user_id` field), or else the fallback approver.

**What the approver sees.** The request shows what the tool will do, so that
the approver understands it: its arguments, with the names of the records their
ids refer to (when the model of the record or of the tool has a relational field
named like the argument), read with the access rights of whoever opens the
request. A tool can also describe its calls in plain words, with a method named
after its function plus `_describe`:

```python
def _ai_create_lead(self, name=None, user_id=None):
    ...

def _ai_create_lead_describe(self, name=None, user_id=None):
    user = self.env["res.users"].browse(user_id)
    return f"Create the lead {name}, assigned to {user.display_name}"
```

It receives the same arguments as the tool function and must only read data: it
runs every time the request is displayed. Its arguments are not trusted (an LLM
wrote them) and it runs with the rights of whoever opens the request, an
administrator included: never use them to pick a model, a method or a field.

**What the records say.** A created document gets an internal note naming who
requested and who approved the action, with a link to the request. A modified
document gets a single message with the same text and its changes: Odoo's own
tracking message when it logs one, also naming the changed fields it does not
track, or else a note of its own. When Odoo sends that tracking message to
external followers (customers), it only says "Proposed by an AI and approved by
...", and the internal details go in a separate internal note. The request lists
these documents in its *Affected Records* tab.

**Where the requests are.** In *Settings > Technical > AI > AI Tool Requests*.
A scheduled action marks the requests past their expiration date as expired.

**For integrations.** Through the context of the tool call they can set:

- `ai_tool_confirm_expiration_hours`: the expiration of this request, instead
  of the instance default.
- `ai_tool_origin`: a label for the integration that made the call.

**Security notes.**

- The approver is always decided by the server, from the identity the tool
  runs with and the configuration: never by the AI (the arguments of the call)
  nor by the caller (the context). Otherwise a prompt injection could send the
  request to whoever suits it, and the action would run with their rights.
  Integrations acting on behalf of someone must execute the tool as that user.
- Only internal users can request AI actions. Portal and public users cannot,
  neither directly nor through code running the tool as OdooBot for them (a
  website chatbot).
- The tool runs with the access rights of the approver, never as superuser,
  and in the company the request was made in.
- Requests can only be answered by their approver, from an Odoo web session:
  not through XML-RPC/JSON-RPC (API keys, scripts, agents holding the user's
  credentials) and never from inside an AI tool, so an AI cannot approve its
  own actions.
- An approval is good for one execution: if the approved tool runs an LLM
  itself, that LLM calling the same tool again needs a new confirmation.
- Nobody can edit a request once made. If a module update changes what the tool
  executes, the request fails instead of running something else.
  Administrators can only change the *Human Confirmation* of a tool, not what
  the tool executes.
- The record is not frozen: it may change between the request and its
  approval, and the arguments were proposed for its state at request time.
  Check the record before approving a request that has waited for a while.
- A call identical to a pending request does not create another one: the AI
  gets the pending one back. Each approver receives a limited number of
  requests per hour (see *Configuration*), so that nobody gets flooded.
- Integrations must execute tools through `_execute_tool` (as `ai_connection`
  and MCP servers do), and must never let an LLM call methods of its choice:
  both would skip the confirmation.
