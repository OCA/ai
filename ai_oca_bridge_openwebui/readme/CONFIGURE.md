## OpenWebUI

1. Create an API key in *Settings → Account → API keys*.
2. Make sure the key can access the models and tools that the bridge should
   use.
3. Configure the model, system prompt, knowledge bases and external tools in
   OpenWebUI. Those remain managed there.

## Odoo

1. Go to *AI Bridge → AI Bridge* and create a bridge.
2. Select **OpenWebUI Chat** as the payload type. The module enforces:
   * Chatter usage;
   * Immediate result kind;
   * Post a Message result type.
3. Set the OpenWebUI chat completion URL, for example:
   `https://<openwebui>/api/chat/completions`.
4. Select **Token Authentication** and enter the OpenWebUI API key.
5. In the **OpenWebUI** tab, set the model identifier, optional bridge system
   prompt, history size and timeout.
6. Optionally click **Synchronize models and tools**, then select a model and
   the tools to expose to the request.
7. Create an internal Odoo user, for example *Assistant IA*, and assign the
   bridge to its **AI Bridge** field.
8. Add this user to a Discuss channel. In a direct chat, the assistant answers
   every message. In a channel with more than two members, mention the
   assistant with `@Assistant IA`.

The expected response is an OpenAI-compatible chat completion containing
`choices[0].message.content`.
