This is a module that defines the basic structure of AI Connections.

However, it does not include any extra configurations.

`_run` accepts an optional `on_step` callable, called on every step of
the AI loop (`iteration`, `tool_call`, `tool_result`), so callers can
report progress. It never commits.

With `tool_activity=True`, an `activity` argument is injected in every
tool definition, asking the AI for a short description of what it is
doing. It is removed before running the tool and reported in the steps.
