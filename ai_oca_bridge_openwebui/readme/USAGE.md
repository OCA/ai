## Responsibilities

Odoo stores bridge configuration, checks the invoking user's permissions, and supplies only the context needed by the selected integration. OpenWebUI handles the configured model, knowledge bases, tools, and provider-specific behavior.

## Integration behavior

- Discuss/chatter requests are handled by `ai_oca_bridge_openwebui_discuss` and posted back as the configured AI user.
- Project task descriptions are drafted through a review wizard by `ai_oca_bridge_openwebui_task`; the task is not updated until a user applies the draft.
- HTML editor requests are handled by `ai_oca_bridge_openwebui_web_editor`; it returns the plain-text response expected by Odoo's editor.

Each integration has its own bridge usage and context policy. The OpenWebUI API token is used only by server-side Odoo code and is never sent to the browser.
