Asks a human to confirm the AI tool calls that modify data before they are
executed.

Odoo already checks whether a user *may* do something, and the AI
integrations check *who* is acting. Nothing checks whether anyone actually
*wanted* the AI to do it. With this module, a call to a tool that is not
read-only is not executed: it becomes an **AI tool request** that a user
approves or rejects. The tool only runs once approved, with the access rights
of the approver.

It works at the `ai_tool` level, so it covers every integration that executes
tools (`ai_connection`, MCP servers, ...).
