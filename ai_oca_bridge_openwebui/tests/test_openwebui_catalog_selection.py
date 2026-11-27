# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests import common


class TestOpenWebUICatalogSelection(common.TransactionCase):
    def _response(self, data):
        response = mock.Mock()
        response.json.return_value = data
        response.raise_for_status.return_value = None
        return response

    def test_sync_selects_first_model_when_bridge_has_no_model(self):
        # The database may already contain models synchronized by other bridges.
        self.env["ai.openwebui.model"].search([]).write({"active": False})
        bridge = self.env["ai.bridge"].create(
            {
                "name": "Catalog selection",
                "url": "https://openwebui.example.com/api/chat/completions",
                "auth_type": "token",
                "auth_token": "sk-test",
                "usage": "none",
                "payload_type": "openwebui",
                "result_kind": "immediate",
                "result_type": "none",
            }
        )
        with mock.patch(
            "requests.get",
            side_effect=[
                self._response(
                    {"data": [{"id": "first-model", "name": "First model"}]}
                ),
                self._response([]),
            ],
        ):
            bridge.action_openwebui_sync_catalog()
        self.assertEqual(bridge.openwebui_model_id.external_id, "first-model")
        self.assertEqual(bridge.openwebui_model, "first-model")

    def test_sync_does_not_replace_existing_model(self):
        model = self.env["ai.openwebui.model"].create(
            {"name": "Selected", "external_id": "selected-model"}
        )
        bridge = self.env["ai.bridge"].create(
            {
                "name": "Catalog selection existing",
                "url": "https://openwebui.example.com/api/chat/completions",
                "auth_type": "token",
                "auth_token": "sk-test",
                "usage": "none",
                "payload_type": "openwebui",
                "result_kind": "immediate",
                "result_type": "none",
                "openwebui_model_id": model.id,
            }
        )
        with mock.patch(
            "requests.get",
            side_effect=[
                self._response(
                    {"data": [{"id": "first-model", "name": "First model"}]}
                ),
                self._response([]),
            ],
        ):
            bridge.action_openwebui_sync_catalog()
        self.assertEqual(bridge.openwebui_model_id, model)
