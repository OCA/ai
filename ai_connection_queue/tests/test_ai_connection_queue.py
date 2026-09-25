# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo_test_helper import FakeModelLoader

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.queue_job.tests.common import JobMixin


class TestAiConnectionQueue(JobMixin, TransactionCase):
    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        # Reuse ai_connection's own demo provider (kind="demo") instead of
        # duplicating a fake AI client here.
        from odoo.addons.ai_connection.tests.fake_models import AiConnection

        from .fake_models import ResPartnerNotifyReceiver

        self.loader.update_registry((AiConnection, ResPartnerNotifyReceiver))
        self.addCleanup(self.loader.restore_registry)

    def _run_all_rounds(self, trap):
        """Drive every round the `ai_connection_async` context key enqueues,
        one at a time - each round's execution can itself enqueue the next
        one, so a single `perform_enqueued_jobs()` is not enough in general.
        """
        while trap.enqueued_jobs:
            trap.perform_enqueued_jobs()

    def test_async_run_returns_id_and_completes(self):
        connection = self.env["ai.connection"].create(
            {"name": "Demo Connection", "kind": "demo"}
        )
        with self.trap_jobs() as trap:
            run_id = connection.with_context(ai_connection_async=True)._run(
                "Hello, AI!"
            )
            # The caller gets an id back immediately, not a recordset and
            # not an answer: at this point the first round has only been
            # enqueued, not executed.
            self.assertIsInstance(run_id, int)
            run = self.env["ai.connection.run"].browse(run_id)
            self.assertEqual(run.state, "running")
            self.assertFalse(run.is_done())

            trap.assert_jobs_count(1)
            self._run_all_rounds(trap)

        self.assertTrue(run.is_done())
        self.assertEqual(run.state, "done")
        content, prompt_tokens, completion_tokens, iteration = run.get_result()
        self.assertEqual(content, "This is a demo response to the prompt: Hello, AI!")
        self.assertEqual(iteration, 1)

    def test_async_run_with_tool_spans_multiple_rounds(self):
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create(
            {"name": "Demo Connection", "kind": "demo"}
        )
        with self.trap_jobs() as trap:
            run_id = connection.with_context(ai_connection_async=True)._run(
                "get_date", tools=tool
            )
            run = self.env["ai.connection.run"].browse(run_id)
            self._run_all_rounds(trap)

        self.assertEqual(run.state, "done")
        self.assertEqual(run.iteration, 2)
        self.assertIn("get_date", run.tool_ids.mapped("name"))

    def test_async_run_max_iterations_reports_error_without_raising(self):
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create(
            {"name": "Demo Connection", "kind": "demo"}
        )
        with self.trap_jobs() as trap:
            # Never raises here: by the time max_iterations would be hit,
            # this call has long since returned an id.
            run_id = connection.with_context(ai_connection_async=True)._run(
                "get_date", tools=tool, max_iterations=1
            )
            run = self.env["ai.connection.run"].browse(run_id)
            self._run_all_rounds(trap)

        self.assertEqual(run.state, "error")
        with self.assertRaises(UserError):
            run.get_result()

    def test_async_run_notifies_callback_on_every_round(self):
        from .fake_models import notify_calls

        notify_calls.clear()
        partner = self.env.user.partner_id
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create(
            {"name": "Demo Connection", "kind": "demo"}
        )
        with self.trap_jobs() as trap:
            run_id = connection.with_context(
                ai_connection_async=True,
                ai_connection_notify_model=partner._name,
                ai_connection_notify_res_id=partner.id,
                ai_connection_notify_method="_ai_connection_run_test_callback",
            )._run("get_date", tools=tool)
            self._run_all_rounds(trap)

        run = self.env["ai.connection.run"].browse(run_id)
        self.assertEqual(run.state, "done")
        # One callback per round (this scenario takes 2: the tool call, then
        # the final answer) - not only when the run finishes.
        self.assertEqual(
            notify_calls, [(partner.id, "running", 1), (partner.id, "done", 2)]
        )

    def test_async_run_notifies_model_level_callback(self):
        from .fake_models import notify_model_calls

        notify_model_calls.clear()
        connection = self.env["ai.connection"].create(
            {"name": "Demo Connection", "kind": "demo"}
        )
        with self.trap_jobs() as trap:
            run_id = connection.with_context(
                ai_connection_async=True,
                ai_connection_notify_model="res.partner",
                # ai_connection_notify_res_id deliberately omitted.
                ai_connection_notify_method="_ai_connection_run_test_model_callback",
            )._run("Hello, AI!")
            self._run_all_rounds(trap)

        run = self.env["ai.connection.run"].browse(run_id)
        self.assertEqual(run.state, "done")
        # No record ids: this is the @api.model-style, env[model] call, not
        # bound to any particular res.partner.
        self.assertEqual(notify_model_calls, [((), "done", 1)])

    def test_async_run_requires_notify_model_and_method_together(self):
        connection = self.env["ai.connection"].create(
            {"name": "Demo Connection", "kind": "demo"}
        )
        with self.assertRaises(ValueError):
            connection.with_context(
                ai_connection_async=True, ai_connection_notify_model="res.partner"
            )._run("Hello, AI!")
        with self.assertRaises(ValueError):
            connection.with_context(
                ai_connection_async=True,
                ai_connection_notify_method="_ai_connection_run_test_callback",
            )._run("Hello, AI!")

    def test_sync_run_is_unaffected(self):
        """Without ai_connection_async, behaviour must be exactly
        `ai_connection`'s own - no `ai.connection.run` created, no job
        enqueued. `_run_ai_step` isn't even overridden as far as this is
        concerned; it just falls through to `super()` every round."""
        connection = self.env["ai.connection"].create(
            {"name": "Demo Connection", "kind": "demo"}
        )
        with self.trap_jobs() as trap:
            response = connection._run("Hello, AI!")
            trap.assert_jobs_count(0)
        self.assertEqual(
            response[0], "This is a demo response to the prompt: Hello, AI!"
        )
        self.assertFalse(self.env["ai.connection.run"].search([]))
