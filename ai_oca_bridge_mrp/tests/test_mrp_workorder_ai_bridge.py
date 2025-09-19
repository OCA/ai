# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests.common import TransactionCase


class TestMrpAiBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create necessary MRP data
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "product",
            }
        )

        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.product.product_tmpl_id.id,
                "product_qty": 1,
            }
        )

        cls.workcenter = cls.env["mrp.workcenter"].create(
            {
                "name": "Test Workcenter",
            }
        )

        cls.operation = cls.env["mrp.routing.workcenter"].create(
            {
                "name": "Test Operation",
                "bom_id": cls.bom.id,
                "workcenter_id": cls.workcenter.id,
            }
        )

        # Create a production order
        cls.production = cls.env["mrp.production"].create(
            {
                "name": "Test Production",
                "product_id": cls.product.id,
                "product_qty": 1,
                "bom_id": cls.bom.id,
            }
        )

        cls.bridge_create = cls.env["ai.bridge"].create(
            {
                "name": "MRP Workorder AI Bridge - Create",
                "description": "<p>Test bridge for MRP workorder creation</p>",
                "model_id": cls.env.ref("mrp.model_mrp_workorder").id,
                "usage": "ai_thread_create",
                "url": "https://api.example.com/ai/mrp/create",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("mrp.field_mrp_workorder__name").id,
                            cls.env.ref("mrp.field_mrp_workorder__state").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_write = cls.env["ai.bridge"].create(
            {
                "name": "MRP Workorder AI Bridge - Update",
                "description": "<p>Test bridge for MRP workorder updates</p>",
                "model_id": cls.env.ref("mrp.model_mrp_workorder").id,
                "usage": "ai_thread_write",
                "url": "https://api.example.com/ai/mrp/update",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("mrp.field_mrp_workorder__name").id,
                            cls.env.ref("mrp.field_mrp_workorder__state").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_unlink = cls.env["ai.bridge"].create(
            {
                "name": "MRP Workorder AI Bridge - Delete",
                "description": "<p>Test bridge for MRP workorder deletion</p>",
                "model_id": cls.env.ref("mrp.model_mrp_workorder").id,
                "usage": "ai_thread_unlink",
                "url": "https://api.example.com/ai/mrp/delete",
                "auth_type": "none",
                "payload_type": "none",
                "result_type": "none",
                "result_kind": "immediate",
            }
        )

    def test_mrp_workorder_create_bridge(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Workorder created"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            workorder = self.env["mrp.workorder"].create(
                {
                    "name": "Test Workorder",
                    "workcenter_id": self.workcenter.id,
                    "production_id": self.production.id,
                    "product_uom_id": self.product.uom_id.id,
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_create.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/mrp/create")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), workorder.id)
            self.assertEqual(record.get("name"), "Test Workorder")

    def test_mrp_workorder_write_bridge(self):
        self.bridge_create.active = False
        workorder = self.env["mrp.workorder"].create(
            {
                "name": "Test Workorder for Update",
                "workcenter_id": self.workcenter.id,
                "production_id": self.production.id,
                "product_uom_id": self.product.uom_id.id,
            }
        )
        self.bridge_create.active = True
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Workorder updated"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            workorder.write(
                {
                    "name": "Updated Workorder",
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_write.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/mrp/update")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), workorder.id)
            self.assertEqual(record.get("name"), "Updated Workorder")

    def test_mrp_workorder_unlink_bridge(self):
        self.bridge_create.active = False
        workorder = self.env["mrp.workorder"].create(
            {
                "name": "Test Workorder for Deletion",
                "workcenter_id": self.workcenter.id,
                "production_id": self.production.id,
                "product_uom_id": self.product.uom_id.id,
            }
        )
        self.bridge_create.active = True
        workorder_id = workorder.id
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Workorder deleted"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            workorder.unlink()
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_unlink.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/mrp/delete")
            self.assertEqual(kwargs["json"].get("_id", False), workorder_id)

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
            workorder = self.env["mrp.workorder"].create(
                {
                    "name": "Complete Test Workorder",
                    "workcenter_id": self.workcenter.id,
                    "production_id": self.production.id,
                    "product_uom_id": self.product.uom_id.id,
                }
            )
            workorder.write(
                {
                    "name": "Updated Complete Test Workorder",
                }
            )
            workorder.unlink()

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
