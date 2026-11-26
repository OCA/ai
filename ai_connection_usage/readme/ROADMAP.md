- The caps are soft limits. They are checked before each call, so the call
  that crosses a cap is still made, and calls running at the same time can all
  pass the check: the overshoot is at most one call per concurrent request.
  Serializing the calls of a company (a lock held during the provider call,
  up to its timeout) would make every AI feature of the company wait on the
  slowest one, and was left out on purpose.
- A failed call is logged with cost 0. Providers usually do not bill a
  request that fails, but one that times out after generating may be billed.
- Costs come from the token counts reported by the provider and the prices
  configured on the connection; they are an estimate, not an invoice.
