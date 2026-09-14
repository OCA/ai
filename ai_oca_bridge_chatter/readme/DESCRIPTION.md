This module allows usage of LLM chatbots inside Odoo.

The logic of the chatbot should be defined in an external system like n8n.

When a user replies to a Discuss message and mentions a bot, the chatter
payload includes the quoted parent message so the agent can evaluate it
without receiving the rest of the channel history.
