This module runs `ai.connection` conversations through `queue_job`, one job
per round, instead of blocking the calling worker until a final answer
comes back.

It is enabled per call through context, without changing `ai.connection`'s
own methods, and it can also notify a caller-chosen record or model after
every round, not only when the conversation finishes.

Check `ai.connection.run` to follow the state of an asynchronous
conversation.
