To configure this module, you need to create 2 parameters:

- *ai_oca_native_generate_openai.url*: Base URL of the API, like `https://llm.example.com/v1`
- *ai_oca_native_generate_openai.model*: Model to use

Optionally, you can also set:

- *ai_oca_native_generate_openai.api_key*: API key, if the server requires one
- *ai_oca_native_generate_openai.temperature*: Temperature of the model
- *ai_oca_native_generate_openai.timeout*: Timeout of the request in seconds (60 by default)

If the URL or the model are not set, the standard Odoo IAP service is used.
