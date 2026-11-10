## OpenWebUI

1. Create an API key in *Settings → Account → API keys*.
2. The API key must belong to the OpenWebUI user who will see the Odoo
   conversations and must have access to the selected model and web-search
   features.
3. Enable and configure Web Search in OpenWebUI, including a search engine
   and its credentials where required.
4. Use a model with Native Function Calling / Agentic Mode enabled. Built-in
   web tools are subject to OpenWebUI permissions, model capabilities and
   global administrator settings.
5. Configure the model, system prompt, knowledge bases and external tools in
   OpenWebUI. OpenWebUI remains the source of truth for these features.

## Odoo

1. Go to *AI Bridge → AI Bridge* and create or open a bridge.
2. Select **OpenWebUI Chat** as the payload type. The module enforces:
   * Chatter usage;
   * Immediate result kind;
   * Post a Message result type.
3. Set the OpenWebUI URL, for example:
   `https://<openwebui>/api/chat/completions`.
4. Select **Token Authentication** and enter the OpenWebUI API key.
5. In the **OpenWebUI** tab, select the synchronized model.
6. Enable **Enable Web Search** when Gérard must be able to search current
   information.
7. Select **Keep OpenWebUI Conversation** when the OpenWebUI user must be
   able to review the original question, the answer, tool activity and
   sources after the request has completed. Disable it only when temporary
   conversations must be deleted after processing.
8. Configure the history size, timeout and optional system prompt.
9. Optionally click **Synchronize models and tools**, then select tools to
   expose to the request. Built-in web search is enabled separately with
   **Enable Web Search**.
10. Create or use an internal Odoo user, for example *Gérard*, and assign the
    bridge to its **AI Bridge** field.
11. Add the Odoo AI user to a Discuss channel. In a direct chat, the assistant
    answers every message. In a channel with more than two members, mention
    the assistant with `@Gérard`.

## User association

The Odoo AI user is the identity that receives Discuss messages and posts the
answer back to Odoo. The OpenWebUI API key identifies the OpenWebUI user who
owns or can access the retained OpenWebUI conversation. Use an API key from
that OpenWebUI user when the user must inspect the conversation and its web
sources.

## Web-search prerequisites

Web search requires all of the following:

- OpenWebUI Web Search enabled globally;
- a configured search engine and credentials, if required;
- permission for the API-key user to use web search;
- a model allowing Native Function Calling / Agentic Mode;
- **Enable Web Search** checked on the Odoo bridge.
