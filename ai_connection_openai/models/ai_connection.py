# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import logging
import os
from urllib.parse import urlparse

import openai

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config

from odoo.addons.ai_connection.client import AiConnectionClient

_logger = logging.getLogger(__name__)

#: odoo.conf option: environment variables a connection may read its key from.
#: Comma separated entries ``NAME`` or ``PREFIX*``, each optionally pinned to
#: the only host the key may be sent to: ``NAME@host``. Empty (the default): no
#: variable is allowed. It lives outside the database on purpose, so that a
#: database administrator cannot point a connection at any other variable of
#: the server process, nor send a pinned key anywhere else.
ENV_ALLOWLIST_OPTION = "ai_connection_openai_env_allowlist"


class OpenaiClient(AiConnectionClient):
    def __init__(
        self,
        tools,
        url,
        model,
        api_key,
        temperature=None,
        max_completion_tokens=None,
        timeout=None,
    ):
        params = {}
        if url:
            params["base_url"] = url
        if api_key:
            params["api_key"] = api_key
        if timeout:
            params["timeout"] = timeout
        self._client = openai.OpenAI(**params)
        self.model = model
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.tool_definition = []
        for tool in tools or []:
            definition = tool._get_tool_definition()
            input_schema = definition["inputSchema"]
            input_schema["additionalProperties"] = False
            self.tool_definition.append(
                {
                    "type": "function",
                    "function": {
                        "name": definition["name"],
                        "description": definition["description"],
                        "parameters": input_schema,
                    },
                }
            )

    def _get_messages(self, messages):
        return [self._get_message(message) for message in messages]

    def _get_message(self, message):
        if not message.get("files"):
            return message
        new_message = message.copy()
        files = new_message.pop("files")
        content = new_message.get("content")
        new_message["content"] = []
        if content:
            new_message["content"].append({"type": "text", "text": content})
        for file in files:
            if file["mimetype"].startswith("text/"):
                new_message["content"].append(
                    {
                        "type": "text",
                        "text": base64.b64decode(file["content"]).decode("utf-8"),
                    }
                )
            elif file["mimetype"].startswith("image/"):
                new_message["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{file['mimetype']};base64,{file['content']}"
                        },
                    }
                )
            else:
                # This part works should work with OpenAI, but some similar sistems
                # like vLLM do not support it yet
                new_message["content"].append(
                    {
                        "type": "file",
                        "file": {
                            "filename": file["name"],
                            "file_data": file["content"],
                        },
                    }
                )
        return new_message

    def handle_message(self, messages=None, **kwargs):
        params = {}
        if self.max_completion_tokens:
            params["max_completion_tokens"] = self.max_completion_tokens
        response = self._client.chat.completions.create(
            model=self.model,
            messages=self._get_messages(messages),
            tools=self.tool_definition or None,
            temperature=self.temperature,
            **params,
        )
        response_message = response.choices[0].message
        return {
            "message": response_message.model_dump(),
            "tool_calls": [
                {
                    "name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments),
                    "id": tool_call.id,
                }
                for tool_call in response_message.tool_calls or []
            ],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        }


class AiConnection(models.Model):
    _inherit = "ai.connection"

    kind = fields.Selection(
        selection_add=[("openai", "OpenAI")], ondelete={"openai": "cascade"}
    )
    openai_api_key = fields.Char(groups="base.group_system")
    openai_api_key_env = fields.Char(
        string="API Key Environment Variable",
        groups="base.group_system",
        help="Name of an environment variable of the Odoo server holding the "
        "API key. When set, the key is read from it on every call and the "
        "stored API Key is ignored, so the key never enters the database. "
        "The server configuration must allow the name (option "
        "ai_connection_openai_env_allowlist).",
    )
    openai_max_completion_tokens = fields.Integer(
        string="Max Completion Tokens",
        help="Upper bound of tokens generated per request, reasoning included. "
        "Leave empty to use the server default.",
    )
    openai_timeout = fields.Float(
        string="Timeout",
        help="Timeout of each request, in seconds. "
        "Leave empty to use the client default.",
    )

    def _get_client_openai(self, tools):
        # url and model are restricted to administrators: read them as such,
        # so that any user allowed to run the connection can use it
        connection = self.sudo()
        return OpenaiClient(
            tools,
            url=connection.url,
            model=connection.model,
            api_key=self._get_openai_api_key(),
            temperature=self.temperature,
            max_completion_tokens=self.openai_max_completion_tokens,
            timeout=self.openai_timeout,
        )

    @api.model
    def _openai_env_allowlist(self):
        """The allowlist as ``[(pattern, host or None), ...]``.

        A bare ``*`` (with or without host) would allow every variable of the
        process: it is ignored, with a warning.
        """
        value = config.get(ENV_ALLOWLIST_OPTION) or ""
        entries = []
        for item in str(value).split(","):
            item = item.strip()
            if not item:
                continue
            pattern, _sep, host = item.partition("@")
            pattern, host = pattern.strip(), host.strip().lower() or None
            if not pattern or pattern == "*":
                _logger.warning(
                    "%s: entry %r ignored, it would allow every environment "
                    "variable",
                    ENV_ALLOWLIST_OPTION,
                    item,
                )
                continue
            entries.append((pattern, host))
        return entries

    @api.model
    def _openai_env_rule(self, env_name):
        """``(allowed, hosts)``: ``hosts`` is None when any host is allowed."""
        allowed, hosts = False, set()
        for pattern, host in self._openai_env_allowlist():
            if pattern.endswith("*"):
                matches = env_name.startswith(pattern[:-1])
            else:
                matches = env_name == pattern
            if not matches:
                continue
            allowed = True
            if host is None:
                hosts = None
            elif hosts is not None:
                hosts.add(host)
        return allowed, (hosts if allowed else set())

    @api.model
    def _openai_env_allowed(self, env_name):
        return self._openai_env_rule(env_name)[0]

    def _openai_env_not_allowed_error(self, env_name):
        return self.env._(
            "The environment variable %(var)s is not allowed for AI connections. "
            "The server administrator must add it to the %(option)s option of "
            "the Odoo configuration file.",
            var=env_name,
            option=ENV_ALLOWLIST_OPTION,
        )

    def _openai_env_url_error(self, env_name):
        """Why the key of ``env_name`` may not go to this connection's URL.

        False when it may. Checked at every call: the URL is the one thing
        that decides where the key is sent.
        """
        self.ensure_one()
        allowed, hosts = self._openai_env_rule(env_name)
        if not allowed:
            return self._openai_env_not_allowed_error(env_name)
        url = (self.sudo().url or "").strip()
        if hosts is None:
            _logger.warning(
                "%s allows %s without a host: its key may be sent to any URL "
                "(AI connection %s). Pin it as %s@<host>.",
                ENV_ALLOWLIST_OPTION,
                env_name,
                self.id,
                env_name,
            )
        if not url and hosts is None:
            return False  # the client's own default endpoint
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or (hosts is not None and hostname not in hosts)
        ):
            return self.env._(
                "The API key in %(var)s may only be sent over https to %(hosts)s. "
                "The URL of the AI connection %(name)s is not one of them.",
                var=env_name,
                hosts=", ".join(sorted(hosts)) if hosts else "an https URL",
                name=self.name,
            )
        return False

    @api.constrains("openai_api_key_env", "url")
    def _check_openai_api_key_env(self):
        for connection in self.sudo():
            env_name = (connection.openai_api_key_env or "").strip()
            if not env_name:
                continue
            if not self._openai_env_allowed(env_name):
                raise ValidationError(self._openai_env_not_allowed_error(env_name))
            # early feedback only for a pinned host; the call checks again
            if self._openai_env_rule(env_name)[1] is not None:
                error = connection._openai_env_url_error(env_name)
                if error:
                    raise ValidationError(error)

    def _get_openai_api_key(self):
        self.ensure_one()
        env_name = (self.sudo().openai_api_key_env or "").strip()
        if not env_name:
            return self.sudo().openai_api_key
        # Checked at every call too: the server configuration or the URL may
        # have changed since the connection was saved
        error = self._openai_env_url_error(env_name)
        if error:
            raise UserError(error)
        api_key = os.environ.get(env_name)
        if not api_key:
            raise UserError(
                self.env._(
                    "The environment variable %(var)s, which holds the API key "
                    "of the AI connection %(name)s, is not set on the server.",
                    var=env_name,
                    name=self.name,
                )
            )
        return api_key
