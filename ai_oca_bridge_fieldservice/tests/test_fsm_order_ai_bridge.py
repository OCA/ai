# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests.common import TransactionCase


class TestFSMOrderAiBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create FSM Location for testing
        cls.fsm_location = cls.env["fsm.location"].create(
            {
                "name": "Test FSM Location",
                "phone": "123456789",
                "email": "test@example.com",
                "street": "Test Street",
                "city": "Test City",
                "zip": "12345",
                "country_id": cls.env.ref("base.br").id,
                "state_id": cls.env.ref("base.state_br_sp").id,
                "owner_id": cls.env.ref("base.partner_root").id,
            }
        )

        # Create FSM Person for testing
        cls.fsm_person = cls.env["fsm.person"].create(
            {
                "name": "Test FSM Person",
                "phone": "987654321",
                "email": "person@example.com",
            }
        )

        # Create FSM Team for testing
        cls.fsm_team = cls.env["fsm.team"].create(
            {
                "name": "Test FSM Team",
                "company_id": cls.env.company.id,
            }
        )

        # Create FSM Stage for testing
        cls.fsm_stage = cls.env["fsm.stage"].create(
            {
                "name": "Test Stage",
                "stage_type": "order",
                "is_default": True,
                "sequence": 1,
                "company_id": cls.env.company.id,
            }
        )

        cls.bridge_create = cls.env["ai.bridge"].create(
            {
                "name": "FSM Order AI Bridge - Create",
                "description": "<p>Test bridge for FSM order creation</p>",
                "model_id": cls.env.ref("fieldservice.model_fsm_order").id,
                "usage": "ai_thread_create",
                "url": "https://api.example.com/ai/fsm/create",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("fieldservice.field_fsm_order__name").id,
                            cls.env.ref("fieldservice.field_fsm_order__description").id,
                            cls.env.ref(
                                "fieldservice.field_fsm_order__scheduled_date_start"
                            ).id,
                            cls.env.ref(
                                "fieldservice.field_fsm_order__scheduled_duration"
                            ).id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_write = cls.env["ai.bridge"].create(
            {
                "name": "FSM Order AI Bridge - Update",
                "description": "<p>Test bridge for FSM order updates</p>",
                "model_id": cls.env.ref("fieldservice.model_fsm_order").id,
                "usage": "ai_thread_write",
                "url": "https://api.example.com/ai/fsm/update",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("fieldservice.field_fsm_order__name").id,
                            cls.env.ref("fieldservice.field_fsm_order__description").id,
                            cls.env.ref(
                                "fieldservice.field_fsm_order__scheduled_date_start"
                            ).id,
                            cls.env.ref(
                                "fieldservice.field_fsm_order__scheduled_duration"
                            ).id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_unlink = cls.env["ai.bridge"].create(
            {
                "name": "FSM Order AI Bridge - Delete",
                "description": "<p>Test bridge for FSM order deletion</p>",
                "model_id": cls.env.ref("fieldservice.model_fsm_order").id,
                "usage": "ai_thread_unlink",
                "url": "https://api.example.com/ai/fsm/delete",
                "auth_type": "none",
                "payload_type": "none",
                "result_type": "none",
                "result_kind": "immediate",
            }
        )

    def test_fsm_order_create_bridge(self):
        other_bridges = self.env["ai.bridge"].search(
            [
                ("model_id", "=", self.env.ref("fieldservice.model_fsm_order").id),
                ("usage", "=", "ai_thread_create"),
                ("id", "!=", self.bridge_create.id),
            ]
        )
        other_bridges.write({"active": False})

        self.bridge_create.write({"usage": "ai_thread_create"})
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "FSM Order created"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.env["fsm.order"].create(
                {
                    "name": "Test FSM Order",
                    "description": "This is a test FSM order for AI bridge",
                    "location_id": self.fsm_location.id,
                    "person_id": self.fsm_person.id,
                    "team_id": self.fsm_team.id,
                    "stage_id": self.fsm_stage.id,
                    "scheduled_date_start": "2025-01-27 10:00:00",
                    "scheduled_duration": 2.0,
                }
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_fsm_order_write_bridge(self):
        other_bridges = self.env["ai.bridge"].search(
            [
                ("model_id", "=", self.env.ref("fieldservice.model_fsm_order").id),
                ("usage", "=", "ai_thread_write"),
                ("id", "!=", self.bridge_write.id),
            ]
        )
        other_bridges.write({"active": False})

        self.bridge_create.active = False
        fsm_order = self.env["fsm.order"].create(
            {
                "name": "Test FSM Order for Update",
                "description": "Initial description",
                "location_id": self.fsm_location.id,
                "person_id": self.fsm_person.id,
                "team_id": self.fsm_team.id,
                "stage_id": self.fsm_stage.id,
                "scheduled_date_start": "2025-01-27 10:00:00",
                "scheduled_duration": 1.0,
            }
        )
        self.bridge_create.active = True
        self.bridge_write.write({"usage": "ai_thread_write"})
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "FSM Order updated"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            fsm_order.write(
                {
                    "name": "Updated FSM Order",
                    "description": "Updated description for AI bridge test",
                    "scheduled_duration": 3.0,
                }
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_fsm_order_unlink_bridge(self):
        other_bridges = self.env["ai.bridge"].search(
            [
                ("model_id", "=", self.env.ref("fieldservice.model_fsm_order").id),
                ("usage", "=", "ai_thread_unlink"),
                ("id", "!=", self.bridge_unlink.id),
            ]
        )
        other_bridges.write({"active": False})

        self.bridge_create.active = False
        fsm_order = self.env["fsm.order"].create(
            {
                "name": "Test FSM Order for Deletion",
                "description": "Description to be deleted",
                "location_id": self.fsm_location.id,
                "person_id": self.fsm_person.id,
                "team_id": self.fsm_team.id,
                "stage_id": self.fsm_stage.id,
                "scheduled_date_start": "2025-01-27 10:00:00",
                "scheduled_duration": 1.0,
            }
        )
        self.bridge_create.active = True
        self.bridge_unlink.write({"usage": "ai_thread_unlink", "payload_type": "none"})
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "FSM Order deleted"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            fsm_order.unlink()
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_all_bridges_together(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            fsm_order = self.env["fsm.order"].create(
                {
                    "name": "Complete Test FSM Order",
                    "description": "Initial description for complete test",
                    "location_id": self.fsm_location.id,
                    "person_id": self.fsm_person.id,
                    "team_id": self.fsm_team.id,
                    "stage_id": self.fsm_stage.id,
                    "scheduled_date_start": "2025-01-27 10:00:00",
                    "scheduled_duration": 1.0,
                }
            )
            fsm_order.write({"description": "Updated description for complete test"})
            fsm_order.unlink()

            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
