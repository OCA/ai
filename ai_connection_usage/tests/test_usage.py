# Copyright 2026 Nimarosa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unittest
from unittest.mock import patch

import psycopg2
from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from odoo_test_helper import FakeModelLoader

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

LOGGER = "odoo.addons.ai_connection_usage.models.ai_connection"


class TestUsage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loader = FakeModelLoader(cls.env, cls.__module__)
        cls.loader.backup_registry()
        from .fake_models import CALLS, AiConnection

        cls.calls = CALLS
        cls.loader.update_registry((AiConnection,))
        # usage rows are written through registry.cursor(): in test mode it
        # is a TestCursor on this test's transaction
        cls.registry.enter_test_mode(cls.cr)
        cls.company = cls.env.company
        cls.connection = cls.env["ai.connection"].create(
            {
                "name": "Usage Connection",
                "kind": "usage_fake",
                "model": "fake-model",
                "usage_currency_id": cls.company.currency_id.id,
                "usage_input_price": 2.0,
                "usage_output_price": 8.0,
            }
        )
        cls.user = new_test_user(cls.env, login="ai_usage_user")
        cls.other_user = new_test_user(cls.env, login="ai_usage_other")
        cls.usage = cls.env["ai.connection.usage"]

    @classmethod
    def tearDownClass(cls):
        cls.registry.leave_test_mode()
        cls.loader.restore_registry()
        super().tearDownClass()

    def _last_usage(self):
        return self.usage.sudo().search(
            [("connection_id", "=", self.connection.id)], limit=1
        )

    def test_call_is_logged_with_cost(self):
        result = self.connection._run(prompt="hello")
        self.assertEqual(result[0], "Answer to hello")
        usage = self._last_usage()
        self.assertEqual(usage.state, "done")
        self.assertEqual(usage.company_id, self.company)
        self.assertEqual(usage.user_id, self.env.user)
        self.assertEqual(usage.model_name, "fake-model")
        self.assertEqual(usage.prompt_tokens, 1000)
        self.assertEqual(usage.completion_tokens, 500)
        self.assertEqual(usage.iterations, 1)
        # 1000 * 2.0 / 1e6 + 500 * 8.0 / 1e6
        self.assertAlmostEqual(usage.cost, 0.006)
        self.assertAlmostEqual(usage.cost_company, 0.006)
        self.assertGreaterEqual(usage.duration, 0.0)
        self.assertFalse(usage.prompt)
        self.assertFalse(usage.answer)
        self.assertAlmostEqual(self.connection.usage_month_spend, 0.006)
        self.assertEqual(self.connection.usage_count, 1)

    def test_purpose_and_record(self):
        partner = self.env.user.partner_id
        self.connection.with_context(ai_usage_purpose="testing")._run(
            prompt="hello", record=partner
        )
        usage = self._last_usage()
        self.assertEqual(usage.purpose, "testing")
        self.assertEqual(usage.res_model, "res.partner")
        self.assertEqual(usage.res_id, partner.id)

    def test_store_content(self):
        self.connection.usage_store_content = True
        self.connection._run(prompt="hello")
        usage = self._last_usage()
        self.assertEqual(usage.prompt, "hello")
        self.assertEqual(usage.answer, "Answer to hello")

    def test_error_is_logged_and_raised(self):
        # unittest's assertRaises: Odoo's one rolls back to a savepoint, which
        # would also drop the row this test looks for
        with unittest.TestCase.assertRaises(self, ConnectionError):
            self.connection._run(prompt="fail")
        usage = self._last_usage()
        self.assertEqual(usage.state, "error")
        self.assertIn("provider unreachable", usage.error)
        self.assertEqual(usage.cost, 0.0)

    def test_connection_company(self):
        company_b = self.env["res.company"].create({"name": "AI Company B"})
        self.connection.company_id = company_b
        self.connection._run(prompt="hello")
        self.assertEqual(self._last_usage().company_id, company_b)

    def test_cost_converted_to_company_currency(self):
        other = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("id", "!=", self.company.currency_id.id)], limit=1)
        )
        other.active = True
        self.env["res.currency.rate"].create(
            {
                "currency_id": other.id,
                "company_id": self.company.id,
                "name": fields.Date.today() - relativedelta(days=1),
                "rate": 2.0,
            }
        )
        self.env["res.currency.rate"].search(
            [
                ("currency_id", "=", self.company.currency_id.id),
                ("name", ">=", fields.Date.today() - relativedelta(days=1)),
            ]
        ).unlink()
        self.connection.usage_currency_id = other
        self.connection._run(prompt="hello")
        usage = self._last_usage()
        self.assertEqual(usage.currency_id, other)
        self.assertAlmostEqual(usage.cost, 0.006)
        self.assertAlmostEqual(usage.cost_company, 0.003)

    def test_connection_cap(self):
        self.connection.usage_month_cap = 0.01
        self.connection._run(prompt="one")
        self.connection._run(prompt="two")
        calls = len(self.calls)
        with self.assertRaisesRegex(UserError, "monthly spending cap"):
            self.connection._run(prompt="three")
        self.assertEqual(len(self.calls), calls, "The provider must not be called")

    def test_company_cap(self):
        self.company.ai_usage_month_cap = 0.01
        self.connection._run(prompt="one")
        self.connection._run(prompt="two")
        calls = len(self.calls)
        with self.assertRaisesRegex(UserError, "monthly AI spending cap"):
            self.connection._run(prompt="three")
        self.assertEqual(len(self.calls), calls)

    def test_company_cap_ignores_previous_months(self):
        self.company.ai_usage_month_cap = 1.0
        self.usage.sudo().create(
            {
                "connection_id": self.connection.id,
                "company_id": self.company.id,
                "user_id": self.env.uid,
                "date": self.usage._usage_today() - relativedelta(months=1),
                "cost": 50.0,
                "cost_company": 50.0,
            }
        )
        self.connection._run(prompt="hello")
        self.assertEqual(self._last_usage().state, "done")

    def test_company_cap_counts_external_spend(self):
        self.company.ai_usage_month_cap = 1.0
        model = self.env.registry["ai.connection"]
        with patch.object(
            model, "_usage_external_month_spend", return_value=1.0, autospec=True
        ) as hook:
            with self.assertRaisesRegex(UserError, "monthly AI spending cap"):
                self.connection._run(prompt="hello")
        self.assertEqual(hook.call_args.args[1], self.company)

    def test_external_spend_default(self):
        self.assertEqual(
            self.env["ai.connection"]._usage_external_month_spend(
                self.company, fields.Date.today()
            ),
            0.0,
        )

    def test_user_sees_only_own_calls(self):
        self.connection.with_user(self.user)._run(prompt="mine")
        self.connection.with_user(self.other_user)._run(prompt="theirs")
        rows = self.usage.with_user(self.user).search([])
        self.assertEqual(rows.user_id, self.user)
        self.assertEqual(
            len(
                self.usage.search(
                    [("user_id", "in", (self.user | self.other_user).ids)]
                )
            ),
            2,
        )

    def test_user_cannot_change_prices_or_caps(self):
        connection = self.connection.with_user(self.user)
        with self.assertRaises(AccessError):
            connection.write({"usage_input_price": 0.0})
        with self.assertRaises(AccessError):
            connection.read(["usage_month_cap"])
        with self.assertRaises(AccessError):
            self.company.with_user(self.user).read(["ai_usage_month_cap"])
        with self.assertRaises(AccessError):
            self.usage.with_user(self.user).create(
                {
                    "connection_id": self.connection.id,
                    "company_id": self.company.id,
                    "user_id": self.user.id,
                }
            )

    def test_user_cannot_read_stored_content(self):
        self.connection.usage_store_content = True
        self.connection.with_user(self.user)._run(prompt="secret")
        usage = self.usage.with_user(self.user).search([], limit=1)
        with self.assertRaises(AccessError):
            usage.read(["prompt"])

    def test_connection_of_other_company_is_hidden(self):
        company_b = self.env["res.company"].create({"name": "AI Company B"})
        self.connection.company_id = company_b
        self.assertNotIn(
            self.connection, self.env["ai.connection"].with_user(self.user).search([])
        )

    def test_action_view_usage(self):
        action = self.connection.action_view_usage()
        self.assertEqual(action["res_model"], "ai.connection.usage")
        self.assertEqual(action["domain"], [("connection_id", "=", self.connection.id)])

    def test_row_written_through_its_own_cursor(self):
        registry_class = type(self.registry)
        with patch.object(
            registry_class, "cursor", autospec=True, side_effect=registry_class.cursor
        ) as cursor:
            self.connection._run(prompt="hello")
        self.assertTrue(cursor.called)
        self.assertEqual(self._last_usage().state, "done")

    def test_row_falls_back_to_the_caller_transaction(self):
        registry_class = type(self.registry)
        with patch.object(
            registry_class,
            "cursor",
            autospec=True,
            side_effect=psycopg2.OperationalError("no connection available"),
        ):
            self.connection._run(prompt="hello")
        usage = self._last_usage()
        self.assertEqual(usage.state, "done")
        self.assertAlmostEqual(usage.cost, 0.006)

    def test_day_in_configured_timezone(self):
        params = self.env["ir.config_parameter"].sudo()
        with freeze_time("2026-12-01 02:00:00"):
            self.assertEqual(str(self.usage._usage_today()), "2026-12-01")
            params.set_param(
                "ai_connection_usage.timezone", "America/Argentina/Buenos_Aires"
            )
            self.assertEqual(str(self.usage._usage_today()), "2026-11-30")
            self.connection._run(prompt="hello")
            self.assertEqual(str(self._last_usage().date), "2026-11-30")
            params.set_param("ai_connection_usage.timezone", "Not/AZone")
            self.assertEqual(str(self.usage._usage_today()), "2026-12-01")

    def _create_raising_on(self, which):
        """Make ``create`` of the usage log fail on ``which`` cursor(s)."""
        usage_class = type(self.usage)
        original = usage_class.create
        test_cr = self.env.cr

        def create(model, vals_list):
            own = model.env.cr is test_cr
            if which == "both" or (which == "separate" and not own):
                raise ValueError("log refused")
            return original(model, vals_list)

        return patch.object(usage_class, "create", autospec=True, side_effect=create)

    def test_separate_cursor_failure_falls_back(self):
        with self._create_raising_on("separate"):
            result = self.connection._run(prompt="hello")
        self.assertEqual(result[0], "Answer to hello")
        self.assertEqual(self._last_usage().state, "done")

    def test_log_failure_never_breaks_a_successful_call(self):
        with self._create_raising_on("both"), mute_logger(LOGGER):
            result = self.connection._run(prompt="hello")
        self.assertEqual(result[0], "Answer to hello")

    def test_log_failure_keeps_the_provider_error(self):
        with self._create_raising_on("both"), mute_logger(LOGGER):
            with unittest.TestCase.assertRaises(self, ConnectionError):
                self.connection._run(prompt="fail")

    def test_cap_counts_committed_and_own_rows(self):
        """Rows only this transaction sees and rows only committed count."""
        own = self.connection._run(prompt="one") and self._last_usage()
        seen = self.usage._month_rows(
            self.usage._usage_today(), connection=self.connection
        )
        committed_only = {own.id + 10_000_000: 0.004}  # invisible here
        model = type(self.env["ai.connection"])
        with patch.object(model, "_usage_committed_rows", return_value=committed_only):
            total = self.connection._usage_committed_month_spend(
                self.usage._usage_today(), connection=self.connection
            )
        self.assertAlmostEqual(total, 0.004 + sum(seen.values()))
        self.assertAlmostEqual(sum(seen.values()), 0.006)


@tagged("post_install", "-at_install")
class TestUsageRealCommit(TransactionCase):
    """A usage row survives the rollback of the caller's transaction.

    Runs on cursors of its own and COMMITS, outside the test transaction (no
    test mode), so it cleans up after itself; FakeModelLoader is not used
    because its registry changes live in the test transaction only: the
    connection uses no provider at all (``_run`` is patched below the usage
    wrapper).
    """

    def test_row_committed_even_if_the_caller_rolls_back(self):
        registry = self.env.registry
        name = "Usage real commit test"
        kinds = self.env["ai.connection"]._fields["kind"].get_values(self.env)
        if not kinds:
            self.skipTest("no connection kind installed (the provider is patched)")
        with registry.cursor() as cr:
            env = self.env(cr=cr, su=True)
            connection = env["ai.connection"].create({"name": name, "kind": kinds[0]})
            connection_id = connection.id
        try:
            base = type(self.env["ai.connection"]).__mro__
            parent = next(
                klass
                for klass in base
                if "_run" in vars(klass)
                and klass.__module__.endswith("ai_connection.models.ai_connection")
            )
            with patch.object(parent, "_run", return_value=("ok", 10, 5, 1)):
                with registry.cursor() as cr:
                    env = self.env(cr=cr, su=True)
                    env["ai.connection"].browse(connection_id)._run(prompt="x")
                    cr.rollback()  # the caller fails after the call
            with registry.cursor() as cr:
                cr.execute(
                    "SELECT count(*) FROM ai_connection_usage WHERE connection_id = %s",
                    (connection_id,),
                )
                self.assertEqual(cr.fetchone()[0], 1)
        finally:
            with registry.cursor() as cr:
                cr.execute("DELETE FROM ai_connection WHERE id = %s", (connection_id,))
