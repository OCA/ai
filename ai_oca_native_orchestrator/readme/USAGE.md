# Usage

1. Configure AI System Prompt Templates under **Technical > AI > Prompt Templates**.
2. Edit system prompts using the Ace code editor with QWeb template syntax (`<t t-out="user.name"/>`, `<t t-out="res_model"/>`).
3. Configure Agent Personas under **Technical > AI > Personas** to associate specific personas with system prompt templates.
4. When a user sends a message in an AI thread, the Orchestrator Agent automatically plans intent extraction, logs sub-task progress in `ai.task.thread`, and persists structured JSON payloads for tool execution.
