# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase

from ..services import catalog_schema, requirement_extractor


class TestRequirementExtractor(TransactionCase):
    def test_parse_and_validate_drops_hallucinated_keys(self):
        content = '{"pressure_bar": 120, "hallucinated_key": "foo", "weight_kg": null}'
        result = requirement_extractor.parse_and_validate(content, env=self.env)
        self.assertEqual(result["pressure_bar"], 120.0)
        self.assertNotIn("hallucinated_key", result)
        self.assertNotIn("weight_kg", result)

    def test_parse_ignores_noise_and_coerces_types(self):
        content = (
            'Prefix {"motor_power_kw": "2,3", "voltage_v": "230", '
            '"pressure_bar": "120 - 150", "phase": "Single-Phase"} suffix'
        )
        result = requirement_extractor.parse_and_validate(content, env=self.env)
        self.assertEqual(result["motor_power_kw"], 2.3)
        self.assertEqual(result["voltage_v"], 230)
        self.assertEqual(result["pressure_bar"], "120 - 150")
        self.assertEqual(result["phase"], "Single-Phase")

    def test_boolean_normalization(self):
        content = '{"has_detergent_tank": true, "auto_start_stop": "yes"}'
        result = requirement_extractor.parse_and_validate(content, env=self.env)
        self.assertIs(result["has_detergent_tank"], True)
        self.assertIs(result["auto_start_stop"], True)

    def test_build_prompt_contains_schema(self):
        prompt = requirement_extractor._build_user_prompt(
            requirement_text="120 bar", env=self.env
        )
        self.assertIn("pressure_bar", prompt)
        self.assertIn("120 bar", prompt)

    def test_coercers_and_schema_edge_cases(self):
        self.assertEqual(
            catalog_schema.normalize_attr_key("x_pressure_bar"), "pressure_bar"
        )
        self.assertTrue(catalog_schema.get_attributes(env=None))
        attr_custom = self.env["product.attribute"].create({"name": "Nozzle Type"})
        self.env["product.attribute.value"].create(
            {"name": "Rotary", "attribute_id": attr_custom.id}
        )
        block = catalog_schema.get_schema_prompt_block(env=self.env)
        self.assertIn("nozzle_type", block)
        self.assertIn("options: Rotary", block)
        self.assertIsNone(
            catalog_schema.get_attribute_meta("nonexistent", env=self.env)
        )

        # Coercer edge cases
        self.assertIs(requirement_extractor._coerce_boolean("no"), False)
        self.assertIs(requirement_extractor._coerce_boolean(1), True)
        self.assertIs(
            requirement_extractor._coerce_boolean("invalid"),
            requirement_extractor._DROP,
        )
        self.assertIs(
            requirement_extractor._coerce_boolean(3.14),
            requirement_extractor._DROP,
        )
        self.assertIs(
            requirement_extractor._coerce_integer(True),
            requirement_extractor._DROP,
        )
        self.assertEqual(requirement_extractor._coerce_integer("10 - 20"), "10 - 20")
        self.assertIs(
            requirement_extractor._coerce_integer("bad"),
            requirement_extractor._DROP,
        )
        self.assertIs(
            requirement_extractor._coerce_float(True),
            requirement_extractor._DROP,
        )
        self.assertIs(
            requirement_extractor._coerce_float("bad"),
            requirement_extractor._DROP,
        )
        self.assertEqual(requirement_extractor._coerce_char(True), "True")
        self.assertIsNone(requirement_extractor._coerce_char("   "))

        with self.assertRaises(ValueError):
            requirement_extractor._parse_json_response("no braces here")
        res = requirement_extractor._parse_json_response(
            '{broken} {"pressure_bar": 100}'
        )
        self.assertEqual(res["pressure_bar"], 100)
