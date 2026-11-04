# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta
from unittest.mock import patch

import psycopg2
from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.ai_message_import.services.ai_client import AIError
from odoo.addons.ai_message_import.services.quote_schema import SCHEMA_VERSION
from odoo.addons.ai_message_import_purchase.services.purchase_order_builder import (
    PurchaseOrderBuilder,
)

from .common import AiMessagePurchaseCase


@tagged("post_install", "-at_install")
class TestBatch(AiMessagePurchaseCase):
    def test_messages_wait_for_inactivity(self):
        first = self._receive("Te paso el presupuesto")
        second = self._receive("Ojo: la cantidad de tornillos es 50, no 40")
        conversation = first.conversation_id
        self.assertEqual(second.conversation_id, conversation)
        self.assertEqual(conversation.state, "open")
        self.assertGreater(
            conversation.process_after, fields.Datetime.now() + timedelta(minutes=2)
        )
        answer = self._answer(
            self._quote(
                [self._line("Tornillo", 50, product_code="FN-100")],
                message_refs=["M1", "M2"],
                clarifications=["The quantity of screws is 50."],
            )
        )
        with self._ai(answer) as calls:
            # Within the 3 minutes nothing is processed.
            self.env["mail.message.import.conversation"]._cron_process()
            self.assertFalse(calls)
            self._process()
        self.assertEqual(len(calls), 1, "The whole conversation goes in one request")
        request = calls[0][0]["text"]
        self.assertIn("[M1]", request)
        self.assertIn("[M2]", request)
        self.assertIn("50, no 40", request)
        self.assertEqual(conversation.state, "done")
        self.assertEqual(set(conversation.message_ids.mapped("state")), {"processed"})
        quote = conversation.document_ids
        self.assertEqual(quote.message_ids, first | second)
        self.assertEqual(quote.purchase_order_id.order_line.product_qty, 50)
        # A later message starts a new conversation.
        self.assertNotEqual(self._receive("Otra cosa").conversation_id, conversation)

    def test_process_now_waits_for_the_files_on_their_way(self):
        first = self._receive("Te paso el presupuesto")
        conversation = first.conversation_id
        conversation.action_process_now()
        self.assertTrue(conversation.process_requested)
        limit = fields.Datetime.now() + timedelta(seconds=30)
        self.assertGreater(conversation.process_after, fields.Datetime.now())
        self.assertLessEqual(conversation.process_after, limit)
        answer = self._answer(
            self._quote([self._line("Tornillo", 50, product_code="FN-100")])
        )
        with self._ai(answer) as calls:
            self.env["mail.message.import.conversation"]._cron_process()
            self.assertFalse(calls, "The files sent with the text are awaited")
            # The file arrives some seconds later: same conversation, short wait.
            second = self._receive("El PDF del presupuesto")
            self.assertEqual(second.conversation_id, conversation)
            limit = fields.Datetime.now() + timedelta(seconds=30)
            self.assertLessEqual(conversation.process_after, limit)
            self._process()
        self.assertEqual(len(calls), 1)
        self.assertEqual(conversation.state, "done")
        self.assertEqual(conversation.message_ids, first | second)

    def test_process_now_after_the_files_arrived(self):
        message = self._receive("Te paso el presupuesto")
        conversation = message.conversation_id
        conversation.last_message_date = fields.Datetime.now() - timedelta(minutes=1)
        conversation.action_process_now()
        self.assertLessEqual(conversation.process_after, fields.Datetime.now())

    def test_ai_tokens_are_counted(self):
        message = self._receive("Te paso el presupuesto")
        answer = self._answer(
            self._quote([self._line("Tornillo", 50, product_code="FN-100")])
        )
        with self._ai(answer, tokens=1500):
            self._process()
        self.assertEqual(message.conversation_id.ai_tokens, 1500)

    def test_the_module_creates_the_prompt_of_its_type(self):
        prompt = self.env.ref(
            "ai_message_import_purchase.prompt_document_type_purchase"
        )
        self.assertEqual(prompt.code, "document_type.purchase")
        self.assertIn(
            "document_type.purchase",
            self.env["ai.message.import.prompt"]._required_codes(),
        )

    def test_ai_connection_of_the_company_is_used(self):
        conversation = self._receive("Presupuesto").conversation_id
        with self._ai(self._answer()):
            self._process()
        self.assertEqual(conversation.ai_model, "test-model")
        self.assertEqual(conversation.schema_version, SCHEMA_VERSION)
        self.assertIn("Presupuesto", conversation.ai_request)

    def test_without_ai_connection_is_an_incident(self):
        conversation = self._receive("Presupuesto").conversation_id
        self.assertFalse(self.config.ai_configured)
        self._process()
        self.assertEqual(conversation.state, "error")
        self.assertFalse(conversation.next_attempt_date, "Retrying would not help")
        self.assertIn("ai_error", self._incident_types(conversation))
        self.assertIn("No AI connection", conversation.last_error)

    def test_invalid_ai_settings_are_refused(self):
        with self.assertRaises(ValidationError):
            self.config.ai_product_min_confidence = 1.5
        with self.assertRaises(ValidationError):
            self.config.total_tolerance = -1
        with self.assertRaises(ValidationError):
            self.config.max_batch_size_mb = 0

    def test_inactivity_is_configurable(self):
        self.config.inactivity_minutes = 10
        conversation = self._receive("Hola").conversation_id
        self.assertGreater(
            conversation.process_after, fields.Datetime.now() + timedelta(minutes=9)
        )

    def test_single_open_batch_per_sender(self):
        conversation = self._receive("Hola").conversation_id
        with (
            mute_logger("odoo.sql_db"),
            self.assertRaises(IntegrityError),
            self.env.cr.savepoint(),
        ):
            conversation.copy({"name": "copy"})

    def test_batch_in_progress_is_not_taken_twice(self):
        conversation = self._receive("Hola").conversation_id
        conversation.process_after = fields.Datetime.now() - timedelta(minutes=1)
        Batch = self.env["mail.message.import.conversation"]
        claimed = Batch._claim_next()
        self.assertEqual(claimed, conversation)
        self.assertEqual(conversation.state, "processing")
        self.assertEqual(conversation.attempt_count, 1)
        self.assertEqual(conversation.processing_ref, f"{conversation.name}#1")
        # Another worker finds nothing to do.
        self.assertFalse(Batch._claim_next())
        # A message arriving meanwhile opens a new conversation.
        self.assertNotEqual(self._receive("Más").conversation_id, conversation)

    def test_several_quotes_make_several_orders(self):
        other_vendor = self.env["res.partner"].create(
            {"name": "Pinturas Sur SA", "vat": "ESA87654323", "supplier_rank": 1}
        )
        quotes = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")]),
            self._quote(
                [self._line("Glue", 3, product_code="GLU-500")],
                quote_key="Q2",
                quote_number="PS-77",
                partner={"name": "Pinturas Sur", "vat": "A87654323", "confidence": 0.9},
            ),
        )
        self.assertEqual(len(quotes), 2)
        self.assertEqual(set(quotes.mapped("state")), {"done"})
        orders = quotes.purchase_order_id
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders.partner_id, self.vendor | other_vendor)

    @mute_logger(
        "odoo.addons.mail_message_import.models.mail_message_import_conversation"
    )
    def test_errors_are_retried_then_reported(self):
        self.config.max_attempts = 2
        message = self._receive("Presupuesto")
        conversation = message.conversation_id
        with self._ai(AIError("The AI connection Test AI failed (APIError 503).")):
            self._process()
            self.assertEqual(conversation.state, "error")
            self.assertEqual(conversation.attempt_count, 1)
            self.assertTrue(conversation.next_attempt_date)
            self.assertFalse(conversation.incident_ids)
            self._process()
        self.assertEqual(conversation.attempt_count, 2)
        self.assertFalse(conversation.next_attempt_date, "No more attempts")
        self.assertEqual(conversation.incident_ids.incident_type, "ai_error")
        self.assertEqual(conversation.incident_ids.category, "technical")
        self.assertIn("503", conversation.last_error)
        self.assertFalse(conversation.document_ids)
        self.assertEqual(message.state, "queued", "The messages are kept")
        # Once solved, the incident retries the conversation.
        conversation.incident_ids.action_retry()
        with self._ai(
            self._answer(
                self._quote([self._line("Tornillo", 5, product_code="FN-100")])
            )
        ):
            self._process()
        self.assertEqual(conversation.state, "done")
        self.assertEqual(conversation.incident_ids.state, "resolved")
        self.assertTrue(conversation.document_ids.purchase_order_id)

    @mute_logger(
        "odoo.addons.mail_message_import.models.mail_message_import_conversation"
    )
    def test_invalid_answer_is_rejected(self):
        self.config.max_attempts = 1
        conversation = self._receive("Presupuesto").conversation_id
        with self._ai({"schema_version": "0.1", "quotes": []}):
            self._process()
        self.assertEqual(conversation.state, "error")
        self.assertEqual(conversation.incident_ids.incident_type, "invalid_ai_response")
        self.assertFalse(
            self.env["purchase.order"].search(
                [("ai_message_import_sender_id", "=", self.sender.id)]
            )
        )

    def _two_quotes(self):
        return self._answer(
            self._quote([self._line("Tornillo", 5, product_code="FN-100")]),
            self._quote(
                [self._line("Glue", 2, product_code="GLU-500")],
                quote_key="Q2",
                quote_number="P-2",
            ),
        )

    def _failing_second_run(self, exception):
        original_run = PurchaseOrderBuilder.run
        runs = []

        def run(builder):
            runs.append(builder.quote)
            if len(runs) == 2:
                raise exception
            return original_run(builder)

        return patch.object(PurchaseOrderBuilder, "run", run)

    def test_failed_quote_does_not_block_the_others(self):
        conversation = self._receive("Presupuesto").conversation_id
        with (
            mute_logger(
                "odoo.addons.ai_message_import.models.mail_message_import_conversation"
            ),
            self._ai(self._two_quotes()),
            self._failing_second_run(ValueError("crash in the second document")),
        ):
            self._process()
        self.assertEqual(conversation.state, "done")
        first, second = conversation.document_ids.sorted("id")
        self.assertEqual(first.state, "done")
        self.assertTrue(first.purchase_order_id)
        self.assertEqual(second.state, "pending")
        self.assertFalse(second.purchase_order_id)
        incident = second.incident_ids
        self.assertEqual(incident.incident_type, "processing_error")
        self.assertIn("crash in the second document", incident.description)
        self.assertTrue(incident.can_retry)
        # Retried once the cause is solved.
        incident.action_retry()
        self.assertEqual(second.state, "done")
        self.assertEqual(incident.state, "resolved")

    def test_concurrency_error_retries_the_conversation(self):
        conversation = self._receive("Presupuesto").conversation_id
        with (
            mute_logger(
                "odoo.addons.mail_message_import.models.mail_message_import_conversation"
            ),
            self._ai(self._two_quotes()),
            self._failing_second_run(psycopg2.errors.SerializationFailure()),
        ):
            self._process()
        self.assertEqual(conversation.state, "error")
        self.assertTrue(conversation.next_attempt_date)
        self.assertFalse(
            conversation.document_ids, "Everything is rolled back and retried"
        )
        self.assertFalse(
            self.env["purchase.order"].search([("partner_id", "=", self.vendor.id)])
        )

    def test_opening_a_batch_twice_returns_the_open_one(self):
        message = self._receive("Hola")
        conversation = message.conversation_id
        again = self.env["mail.message.import.conversation"]._create_open_conversation(
            message, fields.Datetime.now(), fields.Datetime.now()
        )
        self.assertEqual(again, conversation)
        self.assertEqual(conversation.state, "open")
        self.assertTrue(conversation.name.startswith("MSG/"))

    @mute_logger(
        "odoo.addons.mail_message_import.models.mail_message_import_conversation"
    )
    def test_interrupted_processing_is_recovered(self):
        conversation = self._receive("Presupuesto").conversation_id
        conversation.write(
            {
                "state": "processing",
                "attempt_count": 1,
                "processing_start": fields.Datetime.now() - timedelta(hours=1),
            }
        )
        self.env["mail.message.import.conversation"]._recover_stale()
        self.assertEqual(conversation.state, "error")
        self.assertTrue(conversation.next_attempt_date)
        with self._ai(
            self._answer(
                self._quote([self._line("Tornillo", 5, product_code="FN-100")])
            )
        ):
            self._process()
        self.assertEqual(conversation.state, "done")

    def test_conversation_without_quote(self):
        conversation = self._receive("Hola, ¿qué tal?").conversation_id
        with self._ai(self._answer(unrelated_message_refs=["M1"])):
            self._process()
        self.assertEqual(conversation.state, "done")
        self.assertFalse(conversation.document_ids)
        self.assertFalse(
            conversation.incident_ids, "A simple greeting is not an incident"
        )

    def test_unsupported_file_is_reported(self):
        message = self._receive(
            files=[
                {
                    "name": "old.doc",
                    "raw": b"\xd0\xcf\x11\xe0" + b"\x00" * 64,
                    "mimetype": "application/msword",
                }
            ]
        )
        with self._ai(self._answer()) as calls:
            self._process()
        self.assertFalse(calls, "Nothing readable was sent to the AI")
        incident = message.conversation_id.incident_ids
        self.assertEqual(incident.incident_type, "unsupported_file")
        self.assertIn(".docx", incident.description)
