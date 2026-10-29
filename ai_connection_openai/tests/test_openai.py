# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from openai.types.chat import ChatCompletion

from odoo.tests.common import TransactionCase


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
