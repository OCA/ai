## Odoo

1. Install `ai_oca_bridge_openwebui`.
2. Create an AI Bridge with payload type **OpenWebUI Chat**.
3. Configure the OpenWebUI chat-completions URL, token authentication, and model identifier. Model/tool catalog synchronization is optional; manual model IDs are supported.
4. Install one or more use-case addons and select the corresponding **Usage** on its bridge:
   - **Chatter** for `ai_oca_bridge_openwebui_discuss`;
   - **Project Task Description** for `ai_oca_bridge_openwebui_task`;
   - **HTML Editor** for `ai_oca_bridge_openwebui_web_editor`.
5. Keep the API token server-side and restrict bridge records to authorized groups.

The provider addon only stores shared connection/configuration and exposes server-side request helpers. It does not run an LLM call until an integration addon invokes it.
