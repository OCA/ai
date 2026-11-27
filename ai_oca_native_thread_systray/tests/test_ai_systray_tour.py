# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestAiSystrayTour(HttpCase):
    def test_ai_systray_tour(self):
        admin_user = self.env.ref("base.user_admin")
        partner = self.env["res.partner"].create({"name": "Systray Tour Partner"})
        thread = self.env["ai.thread"].create(
            {
                "name": "Systray Tour Thread",
                "res_model": "res.partner",
                "res_id": partner.id,
                "user_id": admin_user.id,
            }
        )
        self.env["ai.message"].create(
            {
                "thread_id": thread.id,
                "role": "assistant",
                "content": "Hello from Systray Tour",
                "status": "processing",
            }
        )

        self.start_tour("/odoo", "ai_systray_tour", login="admin")
