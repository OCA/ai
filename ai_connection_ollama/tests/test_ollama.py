# Copyright 2026 SDi - Angel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from ..models.ai_connection import OllamaClient


class TestOllamaConnection(TransactionCase):
    def setUp(self):
        super().setUp()
        self.connection = self.env["ai.connection"].create(
            {
                "name": "Test Ollama",
                "kind": "ollama",
                "url": "http://localhost:11434",
                "model": "llama3",
            }
        )

    def test_ollama_kind_registered(self):
        self.assertEqual(self.connection.kind, "ollama")

    def test_ollama_options_field(self):
        self.connection.ollama_options = {"num_ctx": 4096}
        self.assertEqual(self.connection.ollama_options, {"num_ctx": 4096})

    def test_ollama_run(self):
        fake_response = {
            "message": {
                "role": "assistant",
                "content": "Hello from Ollama!",
            },
            "tool_calls": [],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
            },
        }
        with patch(
            "odoo.addons.ai_connection_ollama.models.ai_connection"
            ".OllamaClient.handle_message",
            return_value=fake_response,
        ):
            result = self.connection._run("Hi")
        self.assertEqual(result[0], "Hello from Ollama!")
        self.assertEqual(result[1], 10)
        self.assertEqual(result[2], 5)
        self.assertEqual(result[3], 1)

    def test_get_client_ollama(self):
        client = self.connection._get_client_ollama(tools=None)
        self.assertEqual(client.model, "llama3")
        self.assertEqual(client.options, {})

    def test_get_client_ollama_with_options(self):
        self.connection.ollama_options = {"num_ctx": 2048}
        client = self.connection._get_client_ollama(tools=None)
        self.assertEqual(client.options, {"num_ctx": 2048})


class TestOllamaClient(TransactionCase):
    def test_client_default_url(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        self.assertEqual(client.model, "llama3")
        self.assertEqual(client.options, {})
        self.assertEqual(client.tool_definition, [])

    def test_client_with_api_key(self):
        client = OllamaClient(
            tools=None,
            url="http://remote:11434",
            model="llama3",
            api_key="secret-key",
        )
        self.assertEqual(client.model, "llama3")
        self.assertIsNotNone(client._client)

    def test_client_tool_definitions(self):
        tool = MagicMock()
        tool._get_tool_definition.return_value = {
            "name": "get_date",
            "description": "Get current date",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        }
        client = OllamaClient(tools=[tool], url=None, model="llama3")
        self.assertEqual(len(client.tool_definition), 1)
        self.assertEqual(client.tool_definition[0]["type"], "function")
        self.assertEqual(client.tool_definition[0]["function"]["name"], "get_date")
        self.assertEqual(
            client.tool_definition[0]["function"]["description"],
            "Get current date",
        )

    def test_handle_message(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        client._client = MagicMock()
        client._client.chat.return_value = {
            "message": {
                "role": "assistant",
                "content": "Test response",
            },
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        result = client.handle_message(messages=[{"role": "user", "content": "Hello"}])
        self.assertEqual(result["message"]["content"], "Test response")
        self.assertEqual(result["usage"]["prompt_tokens"], 10)
        self.assertEqual(result["usage"]["completion_tokens"], 5)
        self.assertEqual(result["tool_calls"], [])
        client._client.chat.assert_called_once()

    def test_handle_message_with_tool_calls(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        client._client = MagicMock()
        client._client.chat.return_value = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_date",
                            "arguments": {"date": "2026-01-01"},
                        }
                    }
                ],
            },
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        result = client.handle_message(
            messages=[{"role": "user", "content": "get date"}]
        )
        self.assertEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["name"], "get_date")
        self.assertEqual(result["tool_calls"][0]["arguments"], {"date": "2026-01-01"})

    def test_adapt_message_image_file(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        msg = {
            "role": "user",
            "content": "describe this",
            "files": [
                {
                    "name": "photo.jpg",
                    "content": "base64data",
                    "mimetype": "image/jpeg",
                }
            ],
        }
        result = client._adapt_message(msg)
        self.assertEqual(result["images"], ["base64data"])
        self.assertNotIn("files", result)

    def test_adapt_message_text_file(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        msg = {
            "role": "user",
            "content": "analyze this",
            "files": [
                {
                    "name": "data.csv",
                    "content": "col1,col2\n1,2",
                    "mimetype": "text/csv",
                }
            ],
        }
        result = client._adapt_message(msg)
        self.assertNotIn("images", result)
        self.assertIn("data.csv", result["content"])
        self.assertIn("col1,col2", result["content"])

    def test_adapt_message_mixed_files(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        msg = {
            "role": "user",
            "content": "look at these",
            "files": [
                {
                    "name": "photo.png",
                    "content": "imgbase64",
                    "mimetype": "image/png",
                },
                {
                    "name": "notes.txt",
                    "content": "some notes",
                    "mimetype": "text/plain",
                },
            ],
        }
        result = client._adapt_message(msg)
        self.assertEqual(result["images"], ["imgbase64"])
        self.assertIn("notes.txt", result["content"])

    def test_adapt_message_tool_calls_string_args(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_date",
                        "arguments": '{"date": "2026-01-01"}',
                    }
                }
            ],
        }
        result = client._adapt_message(msg)
        self.assertEqual(
            result["tool_calls"][0]["function"]["arguments"],
            {"date": "2026-01-01"},
        )

    def test_adapt_message_tool_calls_invalid_json(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_date",
                        "arguments": "not-valid-json",
                    }
                }
            ],
        }
        result = client._adapt_message(msg)
        self.assertEqual(
            result["tool_calls"][0]["function"]["arguments"], "not-valid-json"
        )

    def test_adapt_message_no_files(self):
        client = OllamaClient(tools=None, url=None, model="llama3")
        msg = {"role": "user", "content": "Hello"}
        result = client._adapt_message(msg)
        self.assertEqual(result, {"role": "user", "content": "Hello"})

    def test_handle_message_calls_with_model_and_options(self):
        client = OllamaClient(
            tools=None,
            url=None,
            model="mistral",
            options={"num_ctx": 4096},
        )
        client._client = MagicMock()
        client._client.chat.return_value = {
            "message": {"role": "assistant", "content": "ok"},
            "prompt_eval_count": 0,
            "eval_count": 0,
        }
        client.handle_message(messages=[{"role": "user", "content": "test"}])
        call_kwargs = client._client.chat.call_args[1]
        self.assertEqual(call_kwargs["model"], "mistral")
        self.assertEqual(call_kwargs["options"], {"num_ctx": 4096})
        self.assertFalse(call_kwargs["stream"])

    def test_run_with_tools(self):
        connection = self.env["ai.connection"].create(
            {
                "name": "Test Ollama",
                "kind": "ollama",
                "url": "http://localhost:11434",
                "model": "llama3",
            }
        )
        tool = self.env.ref("ai_tool.current_date")
        fake_response = {
            "message": {
                "role": "assistant",
                "content": "Today is 2026-01-01",
            },
            "tool_calls": [],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
            },
        }
        with patch(
            "odoo.addons.ai_connection_ollama.models.ai_connection"
            ".OllamaClient.handle_message",
            return_value=fake_response,
        ):
            result = connection._run("what is the date?", tools=tool)
        self.assertEqual(result[0], "Today is 2026-01-01")
        self.assertEqual(result[1], 20)
        self.assertEqual(result[2], 10)
