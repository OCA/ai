# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import os
from unittest.mock import patch

from openai.types.chat import ChatCompletion

from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase
from odoo.tools import config

from odoo.addons.ai_connection_openai.models.ai_connection import (
    ENV_ALLOWLIST_OPTION,
)

LOGGER = "odoo.addons.ai_connection_openai.models.ai_connection"


class TestOpenai(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env["ai.connection"].create(
            {
                "name": "Test OpenAI Connection",
                "kind": "openai",
                "url": "https://myfake.openai.url/v1",
                "model": "gpt-4o",
                "temperature": 0.7,
            }
        )
        cls.result = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4o",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "The answer is 3.",
                    },
                    "finish_reason": "stop",
                }
            ],
        }

    def test_basic_call(self):
        with patch("openai.OpenAI") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = (
                ChatCompletion.model_validate(self.result)
            )
            result = self.connection._run(prompt="How much is 2+1")
            self.assertEqual(result[0], "The answer is 3.")
            mock_client.assert_called_once()

    def test_text_file_call(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test.txt",
                "datas": "VGhpcyBpcyBhIHRlc3QgZmlsZS4=",
                "mimetype": "text/plain",
            }
        )
        with patch("openai.OpenAI") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = (
                ChatCompletion.model_validate(self.result)
            )
            result = self.connection._run(
                prompt="How much is 2+1", attachments=attachment
            )
            self.assertEqual(result[0], "The answer is 3.")
            mock_client.assert_called_once()

    def test_image_file_call(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test.png",
                "datas": "iVBORw0KGgoAAAANSUhEUgAAAAUA\n"
                "AAAAFCAIAAAACDbGyAAAAEklEQVR42mP8z/C/HwAE"
                "/wH+o1kAAAAASUVORK5CYII=",
                "mimetype": "image/png",
            }
        )
        with patch("openai.OpenAI") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = (
                ChatCompletion.model_validate(self.result)
            )
            result = self.connection._run(
                prompt="How much is 2+1", attachments=attachment
            )
            self.assertEqual(result[0], "The answer is 3.")
            mock_client.assert_called_once()

    def test_pdf_file_call(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test.pdf",
                "datas": "iVBORw0KGgoAAAANSUhEUgAAAAUA\n"
                "AAAAFCAIAAAACDbGyAAAAEklEQVR42mP8z/C/HwAE"
                "/wH+o1kAAAAASUVORK5CYII=",
                "mimetype": "application/pdf",
            }
        )
        with patch("openai.OpenAI") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = (
                ChatCompletion.model_validate(self.result)
            )
            result = self.connection._run(
                prompt="How much is 2+1", attachments=attachment
            )
            self.assertEqual(result[0], "The answer is 3.")
            mock_client.assert_called_once()

    def test_temperature_is_sent(self):
        with patch("openai.OpenAI") as mock_client:
            create = mock_client.return_value.chat.completions.create
            create.return_value = ChatCompletion.model_validate(self.result)
            self.connection._run(prompt="How much is 2+1")
            self.assertEqual(create.call_args.kwargs["temperature"], 0.7)

    def test_limits_not_sent_when_unset(self):
        with patch("openai.OpenAI") as mock_client:
            create = mock_client.return_value.chat.completions.create
            create.return_value = ChatCompletion.model_validate(self.result)
            self.connection._run(prompt="How much is 2+1")
            self.assertNotIn("max_completion_tokens", create.call_args.kwargs)
            self.assertNotIn("timeout", mock_client.call_args.kwargs)

    def test_limits_sent_when_set(self):
        self.connection.write(
            {"openai_max_completion_tokens": 256, "openai_timeout": 30.0}
        )
        with patch("openai.OpenAI") as mock_client:
            create = mock_client.return_value.chat.completions.create
            create.return_value = ChatCompletion.model_validate(self.result)
            self.connection._run(prompt="How much is 2+1")
            self.assertEqual(create.call_args.kwargs["max_completion_tokens"], 256)
            self.assertEqual(mock_client.call_args.kwargs["timeout"], 30.0)

    def _allow(self, value):
        return patch.dict(config.options, {ENV_ALLOWLIST_OPTION: value})

    def _call(self, env=None):
        """Run the connection with the key variable set; return the mock."""
        with (
            patch.dict(os.environ, env or {"AI_CONNECTION_TEST_KEY": "env-key"}),
            patch("openai.OpenAI") as mock_client,
        ):
            create = mock_client.return_value.chat.completions.create
            create.return_value = ChatCompletion.model_validate(self.result)
            self.connection._run(prompt="How much is 2+1")
        return mock_client

    def test_api_key_stored(self):
        self.connection.openai_api_key = "stored-key"
        mock_client = self._call(env={})
        self.assertEqual(mock_client.call_args.kwargs["api_key"], "stored-key")

    def test_api_key_from_pinned_variable_right_host(self):
        with self._allow(
            "OTHER_KEY@other.host, AI_CONNECTION_TEST_KEY@MYFAKE.OPENAI.URL"
        ):
            self.connection.write(
                {
                    "openai_api_key": "stored-key",
                    "openai_api_key_env": "AI_CONNECTION_TEST_KEY",
                }
            )
            mock_client = self._call()
        self.assertEqual(mock_client.call_args.kwargs["api_key"], "env-key")

    def test_api_key_prefix_with_host(self):
        with self._allow("AI_CONNECTION_*@myfake.openai.url"):
            self.connection.openai_api_key_env = "AI_CONNECTION_TEST_KEY"
            mock_client = self._call()
        self.assertEqual(mock_client.call_args.kwargs["api_key"], "env-key")

    def _assert_refused(self, url, allow="AI_CONNECTION_TEST_KEY@myfake.openai.url"):
        with self._allow("AI_CONNECTION_TEST_KEY"):
            self.connection.write(
                {"openai_api_key_env": "AI_CONNECTION_TEST_KEY", "url": url}
            )
        secret = "value-that-must-not-leak"
        with (
            self._allow(allow),
            patch.dict(os.environ, {"AI_CONNECTION_TEST_KEY": secret}),
            patch("openai.OpenAI") as mock_client,
        ):
            with self.assertRaises(UserError) as error:
                self.connection._run(prompt="How much is 2+1")
            mock_client.assert_not_called()
        self.assertNotIn(secret, str(error.exception))
        return str(error.exception)

    def test_api_key_pinned_other_host_refused(self):
        message = self._assert_refused("https://evil.example.com/v1")
        self.assertIn("myfake.openai.url", message)

    def test_api_key_pinned_userinfo_trick_refused(self):
        self._assert_refused("https://myfake.openai.url@evil.example.com/v1")
        self._assert_refused("https://user:pw@myfake.openai.url/v1")

    def test_api_key_pinned_http_refused(self):
        self._assert_refused("http://myfake.openai.url/v1")

    def test_api_key_pinned_empty_url_refused(self):
        self._assert_refused("")

    def test_api_key_pinned_host_checked_on_write(self):
        with self._allow("AI_CONNECTION_TEST_KEY@myfake.openai.url"):
            self.connection.openai_api_key_env = "AI_CONNECTION_TEST_KEY"
            with self.assertRaisesRegex(ValidationError, "myfake.openai.url"):
                self.connection.url = "https://evil.example.com/v1"

    def test_api_key_unpinned_entry_warns_at_call_time(self):
        with self._allow("AI_CONNECTION_TEST_KEY"):
            self.connection.openai_api_key_env = "AI_CONNECTION_TEST_KEY"
            with self.assertLogs(LOGGER, "WARNING") as logs:
                mock_client = self._call()
        self.assertEqual(mock_client.call_args.kwargs["api_key"], "env-key")
        self.assertIn("any URL", logs.output[0])
        self.assertNotIn("env-key", logs.output[0])

    def test_api_key_bare_star_is_ignored(self):
        for value in ("*", "*@myfake.openai.url"):
            with self._allow(value):
                with self.assertLogs(LOGGER, "WARNING"):
                    with self.assertRaisesRegex(ValidationError, ENV_ALLOWLIST_OPTION):
                        self.connection.openai_api_key_env = "AI_CONNECTION_TEST_KEY"

    def test_api_key_environment_variable_not_allowed(self):
        with self._allow("AI_CONNECTION_*@myfake.openai.url"):
            with self.assertRaisesRegex(ValidationError, ENV_ALLOWLIST_OPTION):
                self.connection.openai_api_key_env = "PGPASSWORD"

    def test_api_key_environment_variable_empty_allowlist(self):
        with self._allow(""):
            with self.assertRaisesRegex(ValidationError, ENV_ALLOWLIST_OPTION):
                self.connection.openai_api_key_env = "AI_CONNECTION_TEST_KEY"

    def test_api_key_allowlist_checked_at_call_time(self):
        with self._allow("AI_CONNECTION_TEST_KEY@myfake.openai.url"):
            self.connection.openai_api_key_env = "AI_CONNECTION_TEST_KEY"
        message = self._assert_refused("https://myfake.openai.url/v1", allow="")
        self.assertIn(ENV_ALLOWLIST_OPTION, message)

    def test_api_key_environment_missing(self):
        with self._allow("AI_CONNECTION_TEST_KEY@myfake.openai.url"):
            self.connection.openai_api_key_env = "AI_CONNECTION_TEST_KEY"
            with (
                patch.dict(os.environ, {}, clear=False),
                patch("openai.OpenAI") as mock_client,
            ):
                os.environ.pop("AI_CONNECTION_TEST_KEY", None)
                with self.assertRaisesRegex(UserError, "AI_CONNECTION_TEST_KEY"):
                    self.connection._run(prompt="How much is 2+1")
                mock_client.assert_not_called()

    def test_non_administrator_can_run_the_connection(self):
        user = new_test_user(self.env, login="ai_openai_user")
        self.connection.openai_api_key = "stored-key"
        with patch("openai.OpenAI") as mock_client:
            create = mock_client.return_value.chat.completions.create
            create.return_value = ChatCompletion.model_validate(self.result)
            self.env.invalidate_all()
            result = self.connection.with_user(user)._run(prompt="How much is 2+1")
        self.assertEqual(result[0], "The answer is 3.")
        self.assertEqual(mock_client.call_args.kwargs["base_url"], self.connection.url)
        self.assertEqual(create.call_args.kwargs["model"], "gpt-4o")
