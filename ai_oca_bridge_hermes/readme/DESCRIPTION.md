This module integrates Odoo Discuss with Hermes AI Agent, allowing users to chat
with AI assistants directly within Odoo's messaging interface.

**Features:**

- Queue-based message processing with state tracking (pending/processing/done/error)
- Secure webhook authentication via tokens
- Auto-detection of DM chats with AI users
- Typing indicators while AI processes responses
- Rate limiting on poll endpoint
- Extensible architecture for custom handlers (escalation, support, etc.)
- Standalone gateway script for easy deployment
