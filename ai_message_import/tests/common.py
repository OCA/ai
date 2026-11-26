# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import copy
from contextlib import contextmanager
from unittest.mock import patch

from odoo import fields

from odoo.addons.mail_message_import.tests.common import MailMessageImportCase

from ..services.ai_client import AIClient
from ..services.quote_schema import SCHEMA_VERSION

# Prompts of the tests: the module creates them without text.
TEST_PROMPTS = {
    "extraction": 'Extract the documents.\nTypes:\n{types}\nSchema "{version}".',
    "product_choice": "Choose the products the {role} wants. Reasons in {lang}.",
    "document_type.purchase": "A quotation that a vendor issues to the company "
    "of the sender.",
    "document_type.sale": "An order that a customer places with the company of "
    "the sender.",
}


class FakeConnection:
    """An AI connection of OCA/ai, answering ``answers`` one per call."""

    name = "Test AI"
    model = "test-model"

    def __init__(self, *answers, tokens=(0, 0)):
        self.answers = list(answers)
        self.tokens = tokens
        self.calls = []

    def sudo(self):
        return self

    def _run_ai(self, messages, tools=None, record=None, max_iterations=None):
        self.calls.append(messages)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer, self.tokens[0], self.tokens[1], 1


class AiCalls(list):
    """The parts of each request to the mocked AI, with its instructions."""

    def __init__(self):
        super().__init__()
        self.instructions = []
        self.schemas = []


class AiMessageImportCase(MailMessageImportCase):
    """Data and helpers shared by the tests: the AI is mocked, the messages
    are handed over as a channel does."""

    #: Type given by the mocked AI to the documents of ``_quote``.
    DOCUMENT_TYPE = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The notes are written in the language of the company: the tests read
        # them in English, whatever the language of the database.
        cls.company.partner_id.lang = "en_US"
        cls.currency = cls.company.currency_id
        Prompt = cls.env["ai.message.import.prompt"].sudo()
        for code, content in TEST_PROMPTS.items():
            prompt = Prompt.search([("code", "=", code)])
            if not prompt:
                Prompt.create({"name": code, "code": code, "content": content})
            elif not prompt.content:
                prompt.content = content
        cls.sender_partner = cls.env["res.partner"].create(
            {"name": "Acme Client SL", "is_company": True}
        )
        cls.sender.partner_id = cls.sender_partner
        # Class of the settings, to mock what depends on the deployment.
        cls.Config = type(cls.env["mail.message.import.config"])

    def _foreign_currency(self):
        """A currency other than the one of the company, without rates."""
        currency = self.env.ref("base.CHF")
        if currency == self.currency:
            currency = self.env.ref("base.GBP")
        currency.active = True
        currency.rate_ids.unlink()
        return currency

    # ------------------------------------------------------------------
    # AI
    # ------------------------------------------------------------------

    def _line(self, description, quantity, **values):
        line = {"description": description, "quantity": quantity, "confidence": 0.95}
        line.update(values)
        return line

    def _quote(self, lines, **values):
        quote = {
            "quote_key": "Q1",
            "document_type": self.DOCUMENT_TYPE,
            "relation": "new",
            "message_refs": ["M1"],
            "partner": {
                "name": "Ferreteria Norte S.L.",
                "vat": "B12345674",
                "confidence": 0.95,
            },
            "quote_number": "P-2026-001",
            "quote_date": fields.Date.to_string(fields.Date.today()),
            "currency": self.currency.name,
            "lines": lines,
            "confidence": 0.9,
        }
        quote.update(values)
        return quote

    def _answer(self, *quotes, **values):
        answer = {"schema_version": SCHEMA_VERSION, "quotes": list(quotes)}
        answer.update(values)
        return answer

    @contextmanager
    def _ai(self, *answers, tokens=0):
        """Mock the AI connection with the given answers, one per call, each
        one spending ``tokens``."""
        calls = AiCalls()
        pending = list(answers)

        def generate_json(client, system_instruction, parts, schema):
            calls.append(parts)
            calls.instructions.append(system_instruction)
            calls.schemas.append(schema)
            answer = pending.pop(0) if len(pending) > 1 else pending[0]
            if isinstance(answer, Exception):
                raise answer
            return copy.deepcopy(answer), "{}", tokens

        with (
            patch.object(
                self.Config, "_ai_client", lambda config: AIClient(FakeConnection())
            ),
            patch.object(AIClient, "generate_json", generate_json),
        ):
            yield calls

    def _run(self, *quotes, text="Presupuesto adjunto", **answer_values):
        """Receive a message, let the AI answer ``documents`` and process it."""
        message = self._receive(text)
        with self._ai(self._answer(*quotes, **answer_values)):
            self._process()
        return message.conversation_id.document_ids.sorted("id")

    def _incident_types(self, record):
        return set(
            record.incident_ids.filtered(lambda i: i.state == "open").mapped(
                "incident_type"
            )
        )
