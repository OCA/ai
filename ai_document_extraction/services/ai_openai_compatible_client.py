# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import requests

from odoo.addons.ai_connection.client import AiConnectionClient


class AiOpenAICompatibleClient(AiConnectionClient):
    """OpenAI-compatible chat completions client (OpenRouter, Ollama, ...).

    The message list built by the caller is forwarded as-is; provider-specific
    options (num_ctx/keep_alive) are only added when the URL points to Ollama.
    """

    def __init__(
        self,
        url,
        model,
        api_key="",
        num_ctx=None,
        keep_alive=None,
        timeout=300,
    ):
        super().__init__()
        self.url = url
        self.model = model
        self.api_key = api_key or ""
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.timeout = timeout

    @property
    def _is_ollama(self):
        return "ollama" in (self.url or "").lower()

    def handle_message(self, messages=None, temperature=None, **kwargs):
        """Post the messages to /chat/completions and return the raw content."""
        payload = {
            "model": self.model,
            "messages": messages or [],
            "temperature": temperature if temperature is not None else 0.0,
            "stream": False,
        }
        if self._is_ollama:
            if self.num_ctx:
                payload["options"] = {"num_ctx": int(self.num_ctx)}
            if self.keep_alive:
                payload["keep_alive"] = self.keep_alive
        headers = {}
        if self.api_key and self.api_key != "dummy":
            headers["Authorization"] = f"Bearer {self.api_key}"
        url = f"{self.url.rstrip('/')}/chat/completions"
        last_error = None
        for _attempt in range(2):
            try:
                response = requests.post(
                    url, json=payload, headers=headers, timeout=self.timeout
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                if not (content or "").strip():
                    raise ValueError("The vision model returned an empty response.")
                return {
                    "message": {"role": "assistant", "content": content},
                    "tool_calls": [],
                }
            except ValueError as error:
                last_error = error
        raise last_error
