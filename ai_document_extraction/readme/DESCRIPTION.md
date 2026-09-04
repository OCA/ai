This module extracts structured invoice data (partner, invoice number, date and
amounts) from uploaded PDF, JPG or PNG documents by sending the rendered document
image to an OpenAI-compatible vision LLM (e.g. Ollama running `qwen3-vl` or a
cloud provider such as OpenRouter) that returns a strict JSON payload.

The result is applied to a draft vendor bill (`account.move`): partner, date,
reference and a single amount line are set automatically. Processing runs in the
background through `queue_job` so the user interface never blocks. If the
extracted partner name cannot be matched, a wizard lets the user pick or create
the partner.

The LLM is instructed to ignore logo/slogan texts found in the document header
(e.g. a company name drawn inside a logo), to never compute missing values, and to
output `null` for anything it cannot read.
