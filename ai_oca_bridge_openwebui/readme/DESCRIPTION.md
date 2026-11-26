This module provides the shared OpenWebUI provider layer for OCA AI Bridge: server-side credentials, model/tool catalog synchronization, and a reusable non-streaming chat-completion helper.

Use a separate integration addon for each Odoo use case:

- `ai_oca_bridge_openwebui_discuss` for Discuss and chatter;
- `ai_oca_bridge_openwebui_task` for project-task description drafting;
- `ai_oca_bridge_openwebui_web_editor` for the HTML editor's AI text tools.

OpenWebUI remains responsible for model execution and provider-specific behavior. This base addon does not send business records to an LLM by itself.
