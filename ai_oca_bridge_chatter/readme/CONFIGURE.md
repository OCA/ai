On your external AI system create a workflow that will receive messages and will return the call directly.

Here you can see an [example](./static/description/Chat.json) of configuration in n8n.

After that, create a bridge with usage type chatter and payload type chatter.
Then, create a user and assign the bridge to it.

With this configuration, the user will answer automatically using the external systema and will be online permanently.
It can be used on livechat without any issues.
