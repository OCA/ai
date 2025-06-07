# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import common


@common.tagged("post_install", "-at_install")
class TestFrontend(common.HttpCase):
    def test_javascript(self):
        self.browser_js(
            "/web/tests?module=ai_oca_bridge", "", login="admin", timeout=1800
        )
