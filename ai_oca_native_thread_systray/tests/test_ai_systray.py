# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestAiSystray(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Systray Partner"})
        cls.thread = cls.env["ai.thread"].create(
            {
                "name": "Systray Test Thread",
                "res_model": "res.partner",
                "res_id": cls.partner.id,
                "user_id": cls.env.user.id,
            }
        )

    def test_get_user_active_threads_success(self):
        self.env["ai.message"].create(
            {
                "thread_id": self.thread.id,
                "role": "user",
                "content": "Systray user prompt",
                "status": "done",
            }
        )
        self.env["ai.message"].create(
            {
                "thread_id": self.thread.id,
                "role": "assistant",
                "content": "Systray assistant response",
                "status": "processing",
            }
        )

        res = self.env["ai.thread"].get_user_active_threads()
        self.assertTrue(len(res) >= 1)
        target = [t for t in res if t["id"] == self.thread.id][0]
        self.assertEqual(target["name"], "Systray Test Thread")
        self.assertEqual(target["res_model"], "res.partner")
        self.assertEqual(target["res_id"], self.partner.id)
        self.assertEqual(target["record_name"], "Systray Partner")
        self.assertEqual(target["status"], "processing")
        self.assertEqual(target["last_content"], "Systray assistant response")

    def test_get_user_active_threads_missing_record(self):
        thread_missing = self.env["ai.thread"].create(
            {
                "name": "Missing Record Thread",
                "res_model": "res.partner",
                "res_id": 999999,
                "user_id": self.env.user.id,
            }
        )
        res = self.env["ai.thread"].get_user_active_threads()
        target = [t for t in res if t["id"] == thread_missing.id][0]
        self.assertEqual(target["record_name"], "Missing Record Thread")
