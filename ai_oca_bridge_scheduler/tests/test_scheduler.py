# Copyright 2026 Trobz
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests.common import TransactionCase


class TestScheduler(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "test@example.com",
            }
        )
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Test Scheduler Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "none",
                "is_scheduled": True,
                "schedule_interval_number": 1,
                "schedule_interval_type": "days",
            }
        )

    def test_scheduler_creates_cron(self):
        self.assertTrue(self.bridge.cron_id)
        self.assertEqual(self.bridge.cron_id.interval_number, 1)
        self.assertEqual(self.bridge.cron_id.interval_type, "days")
        self.assertTrue(self.bridge.cron_id.active)

    def test_scheduler_cron_deactivated_on_bridge_inactive(self):
        self.assertTrue(self.bridge.cron_id.active)
        self.bridge.active = False
        self.assertFalse(self.bridge.cron_id.active)
        self.bridge.active = True
        self.assertTrue(self.bridge.cron_id.active)

    def test_scheduler_toggle_is_scheduled(self):
        self.assertTrue(self.bridge.cron_id)
        cron = self.bridge.cron_id
        self.bridge.is_scheduled = False
        self.assertFalse(self.bridge.cron_id)
        self.assertFalse(self.env["ir.cron"].search([("id", "=", cron.id)]))
        self.bridge.is_scheduled = True
        self.assertTrue(self.bridge.cron_id)

    def test_scheduler_run(self):
        with mock.patch("requests.post") as mock_post:
            self.bridge._run_schedule()
            mock_post.assert_called()
        executions = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertTrue(executions)
        self.assertIn(self.partner.id, executions.mapped("res_id"))

    def test_scheduler_domain_filtering(self):
        # Domain matches nothing → no executions at all
        self.bridge.domain = "[('id', '=', -1)]"
        with mock.patch("requests.post") as mock_post:
            self.bridge._run_schedule()
            mock_post.assert_not_called()
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )

    def test_scheduler_no_model(self):
        bridge_no_model = self.env["ai.bridge"].create(
            {
                "name": "No Model Bridge",
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "none",
                "is_scheduled": True,
            }
        )
        # Should return silently without error
        bridge_no_model._run_schedule()
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", bridge_no_model.id)]
            )
        )

    def test_scheduler_combined_thread(self):
        """Bridge with usage='thread' + is_scheduled=True: both features work independently."""
        bridge = self.env["ai.bridge"].create(
            {
                "name": "Thread + Scheduled Bridge",
                "model_id": self.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
                "is_scheduled": True,
                "schedule_interval_number": 1,
                "schedule_interval_type": "weeks",
            }
        )
        # Cron is created
        self.assertTrue(bridge.cron_id)
        # Bridge appears in chatter ai_bridge_info
        self.assertIn(bridge.id, [b["id"] for b in self.partner.ai_bridge_info])

    def test_scheduler_unlink_removes_cron(self):
        bridge = self.env["ai.bridge"].create(
            {
                "name": "To Delete Bridge",
                "model_id": self.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "is_scheduled": True,
            }
        )
        cron_id = bridge.cron_id.id
        self.assertTrue(cron_id)
        bridge.unlink()
        self.assertFalse(self.env["ir.cron"].search([("id", "=", cron_id)]))
