This module runs `ai.connection` conversations through `queue_job` instead
of blocking the calling worker until the AI provider produces a final
answer.

It does not change `ai.connection`'s synchronous behaviour at all - it only
adds an opt-in, context-driven way to run a conversation asynchronously and
be notified of its progress.
