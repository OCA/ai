# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests.common import TransactionCase


class TestSaleAiBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create necessary Sale data
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "email": "test@example.com",
            }
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "detailed_type": "consu",
                "list_price": 100.0,
            }
        )

        # Create bridges for sale orders
        cls.bridge_sale_order_create = cls.env["ai.bridge"].create(
            {
                "name": "Sale Order AI Bridge - Create",
                "description": "<p>Test bridge for sale order creation</p>",
                "model_id": cls.env.ref("sale.model_sale_order").id,
                "usage": "ai_thread_create",
                "url": "https://api.example.com/ai/sale_order/create",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("sale.field_sale_order__name").id,
                            cls.env.ref("sale.field_sale_order__partner_id").id,
                            cls.env.ref("sale.field_sale_order__state").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_sale_order_write = cls.env["ai.bridge"].create(
            {
                "name": "Sale Order AI Bridge - Update",
                "description": "<p>Test bridge for sale order updates</p>",
                "model_id": cls.env.ref("sale.model_sale_order").id,
                "usage": "ai_thread_write",
                "url": "https://api.example.com/ai/sale_order/update",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("sale.field_sale_order__name").id,
                            cls.env.ref("sale.field_sale_order__partner_id").id,
                            cls.env.ref("sale.field_sale_order__state").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_sale_order_unlink = cls.env["ai.bridge"].create(
            {
                "name": "Sale Order AI Bridge - Delete",
                "description": "<p>Test bridge for sale order deletion</p>",
                "model_id": cls.env.ref("sale.model_sale_order").id,
                "usage": "ai_thread_unlink",
                "url": "https://api.example.com/ai/sale_order/delete",
                "auth_type": "none",
                "payload_type": "none",
                "result_type": "none",
                "result_kind": "immediate",
            }
        )

        # Create bridges for sale order lines
        cls.bridge_sale_order_line_create = cls.env["ai.bridge"].create(
            {
                "name": "Sale Order Line AI Bridge - Create",
                "description": "<p>Test bridge for sale order line creation</p>",
                "model_id": cls.env.ref("sale.model_sale_order_line").id,
                "usage": "ai_thread_create",
                "url": "https://api.example.com/ai/sale_order_line/create",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("sale.field_sale_order_line__name").id,
                            cls.env.ref("sale.field_sale_order_line__product_id").id,
                            cls.env.ref(
                                "sale.field_sale_order_line__product_uom_qty"
                            ).id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_sale_order_line_write = cls.env["ai.bridge"].create(
            {
                "name": "Sale Order Line AI Bridge - Update",
                "description": "<p>Test bridge for sale order line updates</p>",
                "model_id": cls.env.ref("sale.model_sale_order_line").id,
                "usage": "ai_thread_write",
                "url": "https://api.example.com/ai/sale_order_line/update",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("sale.field_sale_order_line__name").id,
                            cls.env.ref("sale.field_sale_order_line__product_id").id,
                            cls.env.ref(
                                "sale.field_sale_order_line__product_uom_qty"
                            ).id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_sale_order_line_unlink = cls.env["ai.bridge"].create(
            {
                "name": "Sale Order Line AI Bridge - Delete",
                "description": "<p>Test bridge for sale order line deletion</p>",
                "model_id": cls.env.ref("sale.model_sale_order_line").id,
                "usage": "ai_thread_unlink",
                "url": "https://api.example.com/ai/sale_order_line/delete",
                "auth_type": "none",
                "payload_type": "none",
                "result_type": "none",
                "result_kind": "immediate",
            }
        )

    def test_sale_order_create_bridge(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Sale order created"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_create.id)]
                ),
            )
            sale_order = self.env["sale.order"].create(
                {
                    "partner_id": self.partner.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 1,
                                "price_unit": 100.0,
                            },
                        )
                    ],
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_sale_order_create.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/sale_order/create")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), sale_order.id)
            partner_id = record.get("partner_id")
            if isinstance(partner_id, list):
                partner_id = partner_id[0]
            self.assertEqual(partner_id, self.partner.id)

    def test_sale_order_write_bridge(self):
        self.bridge_sale_order_create.active = False
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        self.bridge_sale_order_create.active = True
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Sale order updated"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_write.id)]
                ),
            )
            sale_order.write(
                {
                    "state": "sale",
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_sale_order_write.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/sale_order/update")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), sale_order.id)
            self.assertEqual(record.get("state"), "sale")

    def test_sale_order_unlink_bridge(self):
        self.bridge_sale_order_create.active = False
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        self.bridge_sale_order_create.active = True
        sale_order_id = sale_order.id
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Sale order deleted"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_unlink.id)]
                ),
            )
            sale_order.unlink()
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_sale_order_unlink.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/sale_order/delete")
            self.assertEqual(kwargs["json"].get("_id", False), sale_order_id)

    def test_sale_order_line_create_bridge(self):
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
            }
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "message": "Sale order line created"
            }
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_create.id)]
                ),
            )
            order_line = self.env["sale.order.line"].create(
                {
                    "order_id": sale_order.id,
                    "product_id": self.product.id,
                    "product_uom_qty": 2,
                    "price_unit": 100.0,
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_sale_order_line_create.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(
                args[0], "https://api.example.com/ai/sale_order_line/create"
            )
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), order_line.id)
            product_id = record.get("product_id")
            if isinstance(product_id, list):
                product_id = product_id[0]
            self.assertEqual(product_id, self.product.id)

    def test_sale_order_line_write_bridge(self):
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
            }
        )
        self.bridge_sale_order_line_create.active = False
        order_line = self.env["sale.order.line"].create(
            {
                "order_id": sale_order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            }
        )
        self.bridge_sale_order_line_create.active = True
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "message": "Sale order line updated"
            }
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_write.id)]
                ),
            )
            order_line.write(
                {
                    "product_uom_qty": 3,
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_sale_order_line_write.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(
                args[0], "https://api.example.com/ai/sale_order_line/update"
            )
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), order_line.id)
            self.assertEqual(record.get("product_uom_qty"), 3)

    def test_sale_order_line_unlink_bridge(self):
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
            }
        )
        self.bridge_sale_order_line_create.active = False
        order_line = self.env["sale.order.line"].create(
            {
                "order_id": sale_order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            }
        )
        self.bridge_sale_order_line_create.active = True
        order_line_id = order_line.id
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "message": "Sale order line deleted"
            }
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_unlink.id)]
                ),
            )
            order_line.unlink()
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_sale_order_line_unlink.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(
                args[0], "https://api.example.com/ai/sale_order_line/delete"
            )
            self.assertEqual(kwargs["json"].get("_id", False), order_line_id)

    def test_all_sale_order_bridges_together(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_create.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_write.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_unlink.id)]
                ),
            )
            sale_order = self.env["sale.order"].create(
                {
                    "partner_id": self.partner.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 1,
                                "price_unit": 100.0,
                            },
                        )
                    ],
                }
            )
            sale_order.write(
                {
                    "state": "sale",
                }
            )

            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_create.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_write.id)]
                ),
            )

    def test_all_sale_order_line_bridges_together(self):
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
            }
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_create.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_write.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_unlink.id)]
                ),
            )
            order_line = self.env["sale.order.line"].create(
                {
                    "order_id": sale_order.id,
                    "product_id": self.product.id,
                    "product_uom_qty": 1,
                    "price_unit": 100.0,
                }
            )
            order_line.write(
                {
                    "product_uom_qty": 2,
                }
            )
            order_line.unlink()

            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_create.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_write.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_sale_order_line_unlink.id)]
                ),
            )
