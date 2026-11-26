This module records every call made through an AI Connection and lets
administrators control what those calls cost.

- One usage row per call: connection, company, user, purpose and related
  record, AI model, prompt and completion tokens, cost, duration and error.
  Prompts and answers are **not** stored unless a connection asks for it.
- Prices per connection (per million input and output tokens, in a currency),
  so each row carries its computed cost.
- An optional company on the connection, to know whose spend a call is.
- Optional monthly spending caps, per company and per connection. Once a cap
  is reached the next call is refused with a clear message, before anything is
  sent to the provider.

Usage rows are written in a transaction of their own, so the row of a failed
call is kept even when the caller rolls back.
