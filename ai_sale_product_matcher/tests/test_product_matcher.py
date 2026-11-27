# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
from unittest.mock import patch

from PIL import Image

from odoo.exceptions import UserError
from odoo.orm.model_classes import add_to_registry
from odoo.tests.common import TransactionCase

from ..services import image_preprocessor, product_matcher
from .fake_models import AiConnection, FakeMatcherClient


def _make_png_bytes(width=800, height=600):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(240, 240, 240)).save(buf, format="PNG")
    return buf.getvalue()


class TestProductMatcher(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        orig_bases = cls.registry[AiConnection._name]._base_classes__
        add_to_registry(cls.registry, AiConnection)
        cls.registry._setup_models__(cls.env.cr, [AiConnection._name])
        cls.registry.init_models(
            cls.env.cr, [AiConnection._name], {"models_to_check": True}
        )

        def cleanup_registry():
            model_cls = cls.registry[AiConnection._name]
            model_cls._base_classes__ = orig_bases
            model_cls._setup_done__ = False
            cls.registry._setup_models__(cls.env.cr, [AiConnection._name])

        cls.addClassCleanup(cleanup_registry)
        cls.partner = cls.env["res.partner"].create({"name": "Industrial Buyer"})
        cls.connection = cls.env["ai.connection"].create(
            {
                "name": "Fake Matcher Connection",
                "kind": "fake_matcher",
                "model": "fake-vision-1",
            }
        )
        cls.categ_parent = cls.env["product.category"].create({"name": "Machinery"})
        cls.categ_child = cls.env["product.category"].create(
            {"name": "High Pressure Units", "parent_id": cls.categ_parent.id}
        )
        cls.attr_pressure = cls.env["product.attribute"].create(
            {"name": "Pressure Bar"}
        )
        cls.val_120 = cls.env["product.attribute.value"].create(
            {"name": "120", "attribute_id": cls.attr_pressure.id}
        )
        cls.val_200 = cls.env["product.attribute.value"].create(
            {"name": "200", "attribute_id": cls.attr_pressure.id}
        )
        cls.attr_phase = cls.env["product.attribute"].create({"name": "Phase"})
        cls.val_single = cls.env["product.attribute.value"].create(
            {"name": "Single-Phase", "attribute_id": cls.attr_phase.id}
        )
        cls.val_three = cls.env["product.attribute.value"].create(
            {"name": "Three-Phase", "attribute_id": cls.attr_phase.id}
        )
        cls.product_best = cls.env["product.template"].create(
            {
                "name": "HP-120 Pro",
                "sale_ok": True,
                "list_price": 1250.0,
                "weight": 28.0,
                "categ_id": cls.categ_child.id,
                "attribute_line_ids": [
                    (
                        0,
                        0,
                        {
                            "attribute_id": cls.attr_pressure.id,
                            "value_ids": [(6, 0, [cls.val_120.id])],
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "attribute_id": cls.attr_phase.id,
                            "value_ids": [(6, 0, [cls.val_single.id])],
                        },
                    ),
                ],
            }
        )
        cls.product_other = cls.env["product.template"].create(
            {
                "name": "HP-200 Heavy",
                "sale_ok": True,
                "list_price": 2400.0,
                "weight": 65.0,
                "categ_id": cls.categ_child.id,
                "attribute_line_ids": [
                    (
                        0,
                        0,
                        {
                            "attribute_id": cls.attr_pressure.id,
                            "value_ids": [(6, 0, [cls.val_200.id])],
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "attribute_id": cls.attr_phase.id,
                            "value_ids": [(6, 0, [cls.val_three.id])],
                        },
                    ),
                ],
            }
        )

    def setUp(self):
        super().setUp()
        FakeMatcherClient.response_queue = []
        FakeMatcherClient.last_messages = []

    def test_numeric_and_range_matching(self):
        self.assertTrue(product_matcher._numeric_match(120, 120))
        self.assertTrue(product_matcher._numeric_match(120, 125))
        self.assertFalse(product_matcher._numeric_match(120, 180))
        self.assertTrue(product_matcher._numeric_match(300, "250 - 540"))
        self.assertFalse(product_matcher._numeric_match(100, "250 - 540"))
        self.assertTrue(product_matcher._numeric_match("250 - 540", 300))
        self.assertFalse(product_matcher._numeric_match("250 - 540", 600))
        self.assertEqual(product_matcher._parse_range("250 - 540"), (250.0, 540.0))
        self.assertIsNone(product_matcher._parse_range("120"))

    def test_char_and_boolean_matching(self):
        self.assertTrue(
            product_matcher._char_match("Single-Phase", "Single-Phase (230V)")
        )
        self.assertFalse(product_matcher._char_match("Three-Phase", "Single-Phase"))
        self.assertTrue(
            product_matcher.is_match("has_detergent_tank", True, "yes", env=self.env)
        )
        self.assertFalse(
            product_matcher.is_match("has_detergent_tank", True, "no", env=self.env)
        )

    def test_score_and_rank_products(self):
        score_empty = product_matcher.score_product({}, self.product_best, env=self.env)
        self.assertEqual(score_empty["percent"], 0.0)
        requirements = {
            "pressure_bar": 120,
            "phase": "Single-Phase",
            "weight_kg": 30.0,
        }
        best = product_matcher.find_best_matches(
            requirements,
            self.product_best | self.product_other,
            limit=5,
            env=self.env,
        )
        self.assertEqual(best[0][0], self.product_best)
        self.assertGreater(best[0][1]["match_count"], best[1][1]["match_count"])

    def test_wizard_extraction_matching_and_add_to_order(self):
        self.env.company.ai_sale_matcher_connection_id = self.connection
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        action = order.action_open_ai_requirement_wizard()
        wizard = self.env["ai.sale.requirement.wizard"].browse(action["res_id"])
        attachment = self.env["ir.attachment"].create(
            {
                "name": "customer_spec.pdf",
                "datas": base64.b64encode(_make_png_bytes()),
                "mimetype": "application/pdf",
            }
        )
        wizard.write(
            {
                "attachment_ids": [(6, 0, [attachment.id])],
                "requirement_text": "120 bar single-phase unit",
                "categ_id": self.categ_parent.id,
            }
        )
        pages = [
            Image.new("RGB", (600, 800), color=(255, 255, 255)),
            Image.new("RGB", (600, 800), color=(230, 230, 230)),
        ]
        with (
            patch(
                "odoo.addons.ai_sale_product_matcher.services.image_preprocessor.convert_from_bytes",
                return_value=pages,
            ),
            patch(
                "odoo.addons.ai_sale_product_matcher.models.sale_order.extract_text_from_pdf",
                return_value="120 bar specification text",
            ),
        ):
            wizard.action_extract()
        self.assertEqual(order.ai_requirement_state, "done")
        self.assertEqual(wizard.state, "done")
        self.assertIn("pressure_bar", wizard.requirements_json)
        self.assertEqual(len(FakeMatcherClient.last_messages[-1]["files"]), 2)
        wizard.action_match()
        self.assertTrue(order.ai_match_ids)
        top_match = order.ai_match_ids[0]
        self.assertEqual(top_match.product_tmpl_id, self.product_best)
        top_match.action_add_to_order()
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(
            order.order_line[0].product_id.product_tmpl_id, self.product_best
        )
        mcp_res = order._ai_find_products(
            requirements={"pressure_bar": 120, "phase": "Single-Phase"}
        )
        self.assertTrue(mcp_res["matches"])

    def test_wizard_guards_and_settings(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        wizard = self.env["ai.sale.requirement.wizard"].create({"order_id": order.id})
        with self.assertRaises(UserError):
            wizard.action_extract()
        wizard.requirement_text = "120 bar"
        with self.assertRaises(UserError):
            wizard.action_extract()
        settings = self.env["res.config.settings"].create(
            {"ai_sale_matcher_connection_id": self.connection.id}
        )
        settings.execute()
        self.assertEqual(
            self.env.company.ai_sale_matcher_connection_id, self.connection
        )
        wizard.requirements_json = "{not valid json"
        with self.assertRaises(UserError):
            wizard.action_match()
        wizard.requirements_json = "[1, 2]"
        with self.assertRaises(UserError):
            wizard.action_match()
        wizard.requirements_json = '{"pressure_bar": 120, "weight_kg": null}'
        wizard.action_match()
        self.assertTrue(order.ai_match_ids)

    def test_edge_cases_and_error_flows(self):
        # Numeric, range, char, boolean, and product value edge cases
        self.assertIsNone(product_matcher._parse_range(None))
        self.assertIsNone(product_matcher._extract_number(True))
        self.assertIsNone(product_matcher._extract_number("250 - 540"))
        self.assertIsNone(product_matcher._extract_number("no-digits"))
        self.assertFalse(product_matcher._char_match(None, "a"))
        self.assertTrue(
            product_matcher._char_match("Single Phase Unit", "Unit Single Phase")
        )
        self.assertFalse(product_matcher._numeric_match(None, 10))
        self.assertTrue(product_matcher._numeric_match("10 - 20", "15 - 25"))
        self.assertTrue(product_matcher._numeric_match(0, 0))
        self.assertFalse(product_matcher._numeric_match(0, 5))
        self.assertTrue(product_matcher._numeric_match("abc", "abc"))
        self.assertFalse(product_matcher.is_match("pressure_bar", 120, None))
        self.assertFalse(product_matcher.is_match("pressure_bar", 120, 0))
        self.assertTrue(
            product_matcher.is_match("has_detergent_tank", True, True, env=self.env)
        )
        self.assertTrue(
            product_matcher.is_match("has_detergent_tank", "yes", 1, env=self.env)
        )
        self.assertEqual(
            product_matcher.get_product_value(self.product_best, "categ_id"),
            self.categ_child.name,
        )
        self.assertEqual(
            product_matcher.get_product_value(self.product_best, "name"),
            "HP-120 Pro",
        )
        attr_sel = self.env["product.attribute"].create({"name": "Spray Mode"})
        self.env["product.attribute.value"].create(
            {"name": "Fan Jet", "attribute_id": attr_sel.id}
        )
        self.assertTrue(
            product_matcher.is_match("spray_mode", "Fan Jet", "Fan Jet", env=self.env)
        )
        self.product_other.weight = 0.0
        score = product_matcher.score_product(
            {"weight_kg": 30.0}, self.product_other, env=self.env
        )
        self.assertIn("weight_kg", score["missing_keys"])

        # Image preprocessor edge cases (large PNG resize, empty PDF, non-PDF text)
        png_att = self.env["ir.attachment"].create(
            {
                "name": "large_image.png",
                "datas": base64.b64encode(_make_png_bytes(1600, 1200)),
                "mimetype": "image/png",
            }
        )
        rendered = image_preprocessor.render_attachment_images(self.env, png_att)
        self.assertEqual(len(rendered), 1)
        self.assertEqual(image_preprocessor.extract_text_from_pdf(png_att), "")
        pdf_nonempty = self.env["ir.attachment"].create(
            {
                "name": "sample.pdf",
                "datas": base64.b64encode(b"%PDF-1.4 invalid body"),
                "mimetype": "application/pdf",
            }
        )
        self.assertEqual(image_preprocessor.extract_text_from_pdf(pdf_nonempty), "")
        pdf_empty = self.env["ir.attachment"].new(
            {"name": "empty.pdf", "mimetype": "application/pdf"}
        )
        self.assertEqual(image_preprocessor.extract_text_from_pdf(pdf_empty), "")
        with patch(
            "odoo.addons.ai_sale_product_matcher.services.image_preprocessor.convert_from_bytes",
            return_value=[],
        ):
            with self.assertRaises(ValueError):
                image_preprocessor.render_attachment_images(self.env, pdf_empty)

        # Sale order extraction error & matching edge cases
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        self.env.company.ai_sale_matcher_connection_id = False
        with self.assertRaises(UserError):
            order.action_extract_requirements(requirement_text="120 bar")
        order.ai_connection_id = self.connection
        txt_att = self.env["ir.attachment"].create(
            {"name": "notes.txt", "datas": base64.b64encode(b"hi")}
        )
        with self.assertRaises(UserError):
            order.action_extract_requirements(
                attachment_ids=[txt_att.id], requirement_text=""
            )
        FakeMatcherClient.response_queue = [
            '{"pressure_bar": 120.0}',
        ]
        order.action_extract_requirements(requirement_text="120 bar")
        self.assertEqual(order.ai_requirement_state, "done")
        FakeMatcherClient.response_queue = [
            ValueError("LLM error 1"),
            ValueError("LLM error 2"),
        ]
        with self.assertLogs(
            "odoo.addons.ai_sale_product_matcher.models.sale_order",
            level="WARNING",
        ):
            order.action_extract_requirements(requirement_text="120 bar")
        self.assertEqual(order.ai_requirement_state, "error")
        self.assertIn("LLM error 2", order.ai_requirement_error)

        order.ai_requirement_json = False
        order._ai_run_matching()
        order.ai_requirement_json = "{bad"
        order._ai_run_matching()
        order.ai_requirement_json = "{}"
        order._ai_run_matching()
        res_kw = order._ai_find_products(pressure_bar=120)
        self.assertTrue(res_kw["matches"])
        with self.assertRaises(ValueError):
            order._ai_find_products(requirements="bad")
