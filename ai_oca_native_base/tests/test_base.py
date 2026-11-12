# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestAiBase(TransactionCase):
    def test_ai_base_groups_exist(self):
        user_group = self.env.ref("ai_oca_native_base.group_ai_user")
        admin_group = self.env.ref("ai_oca_native_base.group_ai_admin")
        self.assertTrue(user_group.exists())
        self.assertTrue(admin_group.exists())
