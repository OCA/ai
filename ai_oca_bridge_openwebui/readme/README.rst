AI OCA Bridge OpenWebUI
========================

This module connects an Odoo Discuss AI user to an OpenWebUI user through
OpenWebUI's server-side agentic chat flow.

Odoo remains responsible for users, access rights, Discuss channels and
posting the final answer. OpenWebUI remains responsible for model execution,
web search, tools, knowledge bases, sources and provider-specific reasoning
output.

The bridge creates an OpenWebUI conversation using the Odoo Discuss channel
name, preserves the original question, waits for server-side agentic tools and
posts the final answer back to Discuss. The OpenWebUI conversation can be kept
for review by the OpenWebUI user.

Configuration
-------------

See ``readme/CONFIGURE.md`` for configuration, permissions and web-search
prerequisites.
See ``readme/USAGE.md`` for the agentic flow, conversation visibility and
responsibilities.
