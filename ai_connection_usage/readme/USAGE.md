Nothing changes for the code calling `ai.connection._run`: each call is
logged automatically. Settings > Technical > AI > AI Usage lists the calls,
filtered on the current month, with totals and a pivot by connection and
month. Administrators see every call; other users only see their own.

A caller can name what the call is for with the `ai_usage_purpose` context
key; the `record` given to `_run` is kept as the related record:

```python
connection.with_context(ai_usage_purpose="product_description")._run(
    prompt=prompt, record=product
)
```

Integrators that also pay for AI calls made outside of `ai.connection` can
override `ai.connection._usage_external_month_spend(company, date)` to return
that spend (in the company currency), so the company cap counts it too.
