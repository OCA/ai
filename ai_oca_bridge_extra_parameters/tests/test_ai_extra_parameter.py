from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestAIExtraParameter(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Test Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "test@example.com",
                "vat": "ES0123456789",
                "phone": "+34 2 123 45 67",
            }
        )

        cls.partner_with_children = cls.env["res.partner"].create(
            {
                "name": "Parent Company",
                "email": "parent@example.com",
                "child_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Child Company 1",
                            "email": "child1@example.com",
                            "phone": "+34 2 111 11 11",
                            "city": "Santa Cruz de Tenerife",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Child Company 2",
                            "email": "child2@example.com",
                            "phone": "+34 2 222 22 22",
                            "city": "Barcelona",
                        },
                    ),
                ],
            }
        )

        cls.param_simple = cls.env["ai.extra.parameter"].create(
            {
                "name": "simple_param",
                "expression": "plain text value",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )

        cls.param_single_expr = cls.env["ai.extra.parameter"].create(
            {
                "name": "name_param",
                "expression": "Partner name is: {object.name}",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )

        cls.param_multi_expr = cls.env["ai.extra.parameter"].create(
            {
                "name": "multi_param",
                "expression": "{object.name} - {object.email} - VAT: {object.vat}",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )

        cls.param_bridge_type = cls.env["ai.extra.parameter"].create(
            {
                "name": "bridge_param",
                "expression": "Bridge: {object.name} - Model: {object.model_id.model}",
                "parameter_type": "self",
                "evaluate_type": "expression",
            }
        )

        cls.param_simple_formula = cls.env["ai.extra.parameter"].create(
            {
                "name": "simple_formula",
                "formula": "result = 'Hello from formula'",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )

        cls.param_list_comp_formula = cls.env["ai.extra.parameter"].create(
            {
                "name": "list_comp_formula",
                "formula": """result = [
    {
        'name': child.name,
        'email': child.email,
        'phone': child.phone,
        'city': child.city,
    }
    for child in object.child_ids
]""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )

    def test_simple_parameter_without_expression(self):
        result = self.param_simple.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "plain text value")

    def test_single_expression_evaluation(self):
        result = self.param_single_expr.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Partner name is: Test Partner")

    def test_multiple_expressions_evaluation(self):
        result = self.param_multi_expr.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Test Partner - test@example.com - VAT: ES0123456789")

    def test_expression_with_methods(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "method_param",
                "expression": "Name length: {len(object.name)} - Upper: {object.name.upper()}",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Name length: 12 - Upper: TEST PARTNER")

    def test_parameter_type_self(self):
        result = self.param_bridge_type.evaluate_parameter(obj=self.bridge)
        self.assertEqual(result, "Bridge: Test Bridge - Model: res.partner")

    def test_false_value_handling(self):
        self.partner.email = False
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "none_param",
                "expression": "Email: {object.email}",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Email: False")

    def test_type_conversion(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "type_param",
                "expression": "Int: {int(42.7)} - Bool: {bool(object.name)} - Str: {str(123)}",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Int: 42 - Bool: True - Str: 123")

    def test_cursor_access_prevention(self):
        dangerous_values = [
            "{object.cr}",
            "{object._cr}",
            "{object.env.cr}",
            "{object.env._cr}",
        ]

        for expression in dangerous_values:
            with self.assertRaises(ValidationError) as cm:
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "cursor_access",
                        "expression": expression,
                        "parameter_type": "record",
                        "evaluate_type": "expression",
                    }
                )
            self.assertIn("Access to", str(cm.exception))

    def test_sql_execute_prevention(self):
        dangerous_values = [
            "{object.cr.execute('DELETE FROM res_partner')}",
            "{object._cr.execute('SELECT * FROM res_users')}",
            "{object.env.cr.execute('DROP TABLE res_partner')}",
        ]
        for expression in dangerous_values:
            with self.assertRaises(ValidationError):
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "sql_execute",
                        "expression": expression,
                        "parameter_type": "record",
                        "evaluate_type": "expression",
                    }
                )

    def test_transaction_control_prevention(self):
        dangerous_values = [
            "{object.cr.commit()}",
            "{object._cr.commit()}",
            "{object.env.cr.rollback()}",
            "{object.rollback()}",
        ]

        for expression in dangerous_values:
            with self.assertRaises(ValidationError):
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "transaction_control",
                        "expression": expression,
                        "parameter_type": "record",
                        "evaluate_type": "expression",
                    }
                )

    def test_sudo_prevention(self):
        dangerous_values = [
            "{object.sudo()}",
            "{object.sudo().unlink()}",
            "{object.env.user.sudo()}",
            "{object.partner_id.sudo().write({'name': 'Hacked'})}",
        ]

        for expression in dangerous_values:
            with self.assertRaises(ValidationError):
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "sudo_access",
                        "expression": expression,
                        "parameter_type": "record",
                        "evaluate_type": "expression",
                    }
                )

    def test_cache_and_flush_prevention(self):
        dangerous_values = [
            "{object.invalidate_cache()}",
            "{object.invalidate_cache(['res.partner'])}",
            "{object.flush()}",
            "{object.env.flush_all()}",
        ]
        for expression in dangerous_values:
            with self.assertRaises(ValidationError):
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "cache_ops",
                        "expression": expression,
                        "parameter_type": "record",
                        "evaluate_type": "expression",
                    }
                )

    def test_invalid_variable_names(self):
        invalid_values = [
            "{record.name}",
            "{self.name}",
            "{partner.name}",
            "{obj.name}",
            "{user.name}",
            "{env}",
            "{cr}",
        ]

        for expression in invalid_values:
            with self.assertRaises(ValidationError):
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "invalid_var",
                        "expression": expression,
                        "parameter_type": "record",
                        "evaluate_type": "expression",
                    }
                )

    def test_unbalanced_braces(self):
        invalid_values = [
            "{object.name",
            "object.name}",
            "{{object.name}",
            "{object.name}}",
        ]
        for expression in invalid_values:
            with self.assertRaises(ValidationError):
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "unbalanced",
                        "expression": expression,
                        "parameter_type": "record",
                        "evaluate_type": "expression",
                    }
                )

    def test_empty_and_edge_cases(self):
        with self.assertRaises(ValidationError):
            self.env["ai.extra.parameter"].create(
                {
                    "name": "empty_expr",
                    "expression": "Result: {}",
                    "parameter_type": "record",
                    "evaluate_type": "expression",
                }
            )

        param = self.env["ai.extra.parameter"].create(
            {
                "name": "no_obj",
                "expression": "Static value",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        result = param.evaluate_parameter(obj=None)
        self.assertEqual(result, "Static value")

    def test_complex_expressions(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "complex_expr",
                "expression": (
                    "Name: {object.name.upper() if object.name else 'N/A'} - "
                    "Has email: {bool(object.email)}"
                ),
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Name: TEST PARTNER - Has email: True")

    def test_nested_attribute_access(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "nested_attr",
                "expression": "Model: {object.model_id.model} - Field: {object.model_id.name}",
                "parameter_type": "self",
                "evaluate_type": "expression",
            }
        )
        result = param.evaluate_parameter(obj=self.bridge)
        self.assertEqual(result, "Model: res.partner - Field: Contact")

    def test_string_methods(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "string_methods",
                "expression": (
                    "{object.name.lower()} | {object.name.strip()} | "
                    "{object.name.replace('Test', 'Demo')}"
                ),
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "test partner | Test Partner | Demo Partner")

    def test_prepare_payload_with_extra_parameters(self):
        self.bridge.extra_parameter_ids = [
            (6, 0, [self.param_single_expr.id, self.param_bridge_type.id])
        ]
        payload = self.bridge._prepare_payload(record=self.partner)

        self.assertIn("extra_parameters", payload)
        self.assertEqual(
            payload["extra_parameters"]["name_param"], "Partner name is: Test Partner"
        )
        self.assertEqual(
            payload["extra_parameters"]["bridge_param"],
            "Bridge: Test Bridge - Model: res.partner",
        )

    def test_prepare_payload_sample_mode(self):
        self.bridge.extra_parameter_ids = [(6, 0, [self.param_single_expr.id])]
        payload = self.bridge.with_context(sample_payload=True)._prepare_payload()
        self.assertIn("extra_parameters", payload)
        self.assertIn("Partner name is:", payload["extra_parameters"]["name_param"])

    def test_prepare_payload_sample_mode_no_records(self):
        bridge_empty_model = self.env["ai.bridge"].create(
            {
                "name": "Test Bridge Empty Model",
                "model_id": self.env.ref("base.model_res_partner_title").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
            }
        )

        self.env["res.partner.title"].search([]).unlink()
        bridge_empty_model.extra_parameter_ids = [(6, 0, [self.param_single_expr.id])]
        payload = bridge_empty_model.with_context(
            sample_payload=True
        )._prepare_payload()
        self.assertEqual(payload, {})

    def test_constraint_check_value(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "bad_param",
                    "expression": "{object.sudo().unlink()}",
                    "parameter_type": "record",
                    "evaluate_type": "expression",
                }
            )
        self.assertIn("Parameter 'bad_param':", str(cm.exception))

    def test_validate_parameter_expression_method(self):
        self.assertTrue(self.param_single_expr.validate_parameter_expression())
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "test_param",
                "expression": "{object.name}",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        with self.assertRaises(ValidationError):
            param.expression = "{object.cr.execute('SELECT 1')}"
            param.validate_parameter_expression()

    def test_special_characters_in_expressions(self):
        test_cases = [
            ("Special chars: {object.name} !@#$%", "Special chars: Test Partner !@#$%"),
            ("Unicode: {object.name} 你好", "Unicode: Test Partner 你好"),
            (
                "Quotes: '{object.name}' \"{object.name}\"",
                "Quotes: 'Test Partner' \"Test Partner\"",
            ),
        ]

        for expression, expected in test_cases:
            param = self.env["ai.extra.parameter"].create(
                {
                    "name": "special_char_param",
                    "expression": expression,
                    "parameter_type": "record",
                    "evaluate_type": "expression",
                }
            )
            result = param.evaluate_parameter(obj=self.partner)
            self.assertEqual(result, expected)

    def test_expression_error_handling(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "error_param",
                "expression": "{object.non_existent_field}",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )

        with self.assertRaises(ValidationError) as cm:
            param.evaluate_parameter(obj=self.partner)
        self.assertIn("Error evaluating expression", str(cm.exception))

    def test_chained_forbidden_calls(self):
        dangerous_values = [
            "{object.with_context({}).sudo()}",
            "{object.search([]).sudo().unlink()}",
            "{object.browse(1).sudo().write({})}",
        ]
        for expression in dangerous_values:
            with self.assertRaises(ValidationError):
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "chained_forbidden",
                        "expression": expression,
                        "parameter_type": "record",
                        "evaluate_type": "expression",
                    }
                )

    def test_simple_formula(self):
        result = self.param_simple_formula.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Hello from formula")

    def test_formula_with_object_access(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "object_formula",
                "formula": "result = f'Partner: {object.name}, Email: {object.email}'",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Partner: Test Partner, Email: test@example.com")

    def test_formula_with_record_alias(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "record_alias_formula",
                "formula": "result = record.name.upper()",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "TEST PARTNER")

    def test_formula_list_comprehension(self):
        result = self.param_list_comp_formula.evaluate_parameter(
            obj=self.partner_with_children
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Child Company 1")
        self.assertEqual(result[0]["email"], "child1@example.com")
        self.assertEqual(result[0]["city"], "Santa Cruz de Tenerife")
        self.assertEqual(result[1]["name"], "Child Company 2")
        self.assertEqual(result[1]["email"], "child2@example.com")
        self.assertEqual(result[1]["city"], "Barcelona")

    def test_formula_with_intermediate_variables(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "intermediate_vars_formula",
                "formula": """total_contacts = 0
items = []
for child in object.child_ids:
    phone_digits = len(child.phone.replace(' ', '').replace('+', ''))
    total_contacts += 1
    items.append({
        'name': child.name,
        'phone_digits': phone_digits
    })

result = {
    'items': items,
    'total': total_contacts,
    'average_digits': sum(i['phone_digits'] for i in items) / len(items) if items else 0
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner_with_children)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 2)
        self.assertGreater(result["average_digits"], 0)

    def test_formula_dict_comprehension(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "dict_comp_formula",
                "formula": """result = {
    child.id: {
        'name': child.name,
        'email': child.email,
        'city': child.city or 'Unknown'
    }
    for child in object.child_ids
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner_with_children)
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 2)

    def test_formula_with_conditionals(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "conditional_formula",
                "formula": """if object.email:
    email_domain = object.email.split('@')[1] if '@' in object.email else 'no-domain'
    result = f"Partner has email at {email_domain}"
else:
    result = "Partner has no email"
""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Partner has email at example.com")

    def test_formula_with_builtin_functions(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "builtin_functions_formula",
                "formula": """emails = [child.email for child in object.child_ids]
result = {
    'count': len(emails),
    'sorted': sorted(emails),
    'first': min(emails) if emails else None,
    'last': max(emails) if emails else None,
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner_with_children)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["first"], "child1@example.com")
        self.assertEqual(result["last"], "child2@example.com")

    def test_formula_nested_comprehensions(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "nested_comp_formula",
                "formula": """
fields = ['email', 'phone']
result = []
for child in object.child_ids:
    child_data = []
    for field in fields:
        child_data.append(f"{child.name} - {field}")
    result.append(child_data)
""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner_with_children)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            result[0], ["Child Company 1 - email", "Child Company 1 - phone"]
        )
        self.assertEqual(
            result[1], ["Child Company 2 - email", "Child Company 2 - phone"]
        )

    def test_formula_no_result_assignment(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "no_result_formula",
                    "formula": "a = 5\nb = 10\nc = a + b",
                    "parameter_type": "record",
                    "evaluate_type": "formula",
                }
            )
        self.assertIn(
            "Formula must assign a value to 'result' variable", str(cm.exception)
        )

    def test_formula_empty(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "empty_formula",
                    "formula": "   ",
                    "parameter_type": "record",
                    "evaluate_type": "formula",
                }
            )
        self.assertIn("Formula cannot be empty", str(cm.exception))

    def test_formula_forbidden_operations(self):
        dangerous_formulas = [
            "import os\nresult = os.listdir('/')",
            "result = eval('1+1')",
            "result = exec('print(1)')",
            "result = open('/etc/passwd').read()",
            "result = object.__class__.__name__",
            "result = object.cr.execute('SELECT 1')",
            "result = object.sudo().name",
            "result = object.write({'name': 'Hacked'})",
        ]

        for formula in dangerous_formulas:
            with self.assertRaises(ValidationError):
                self.env["ai.extra.parameter"].create(
                    {
                        "name": "dangerous_formula",
                        "formula": formula,
                        "parameter_type": "record",
                        "evaluate_type": "formula",
                    }
                )

    def test_formula_invalid_syntax(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "invalid_syntax_formula",
                    "formula": "result = if True",
                    "parameter_type": "record",
                    "evaluate_type": "formula",
                }
            )
        self.assertIn("Invalid Python syntax", str(cm.exception))

    def test_formula_undefined_variables(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "undefined_var_formula",
                    "formula": "result = unknown_var + 5",
                    "parameter_type": "record",
                    "evaluate_type": "formula",
                }
            )
        self.assertIn("Undefined variables: unknown_var", str(cm.exception))

    def test_formula_runtime_error(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "runtime_error_formula",
                "formula": "result = 1 / 0",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        with self.assertRaises(ValidationError) as cm:
            param.evaluate_parameter(obj=self.partner)
        self.assertIn("Error executing formula", str(cm.exception))

    def test_formula_complex_data_transformation(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "complex_transform_formula",
                "formula": """cities = {}
for child in object.child_ids:
    city = child.city or 'Unknown'
    if city not in cities:
        cities[city] = []
    cities[city].append({
        'name': child.name,
        'email': child.email
    })

result = {}
for city, companies in cities.items():
    result[city] = {
        'companies': companies,
        'count': len(companies)
    }
""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner_with_children)
        self.assertIsInstance(result, dict)
        self.assertIn("Santa Cruz de Tenerife", result)
        self.assertIn("Barcelona", result)
        self.assertEqual(result["Santa Cruz de Tenerife"]["count"], 1)
        self.assertEqual(result["Barcelona"]["count"], 1)

    def test_formula_with_enumerate_and_zip(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "enumerate_zip_formula",
                "formula": """names = [child.name for child in object.child_ids]
emails = [child.email for child in object.child_ids]

result = {
    'enumerated': [(i, name) for i, name in enumerate(names)],
    'zipped': list(zip(names, emails))
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner_with_children)
        self.assertEqual(result["enumerated"][0], (0, "Child Company 1"))
        self.assertEqual(result["enumerated"][1], (1, "Child Company 2"))
        self.assertEqual(result["zipped"][0], ("Child Company 1", "child1@example.com"))
        self.assertEqual(result["zipped"][1], ("Child Company 2", "child2@example.com"))

    def test_validate_parameter_formula_method(self):
        self.assertTrue(self.param_simple_formula.validate_parameter_formula())

        param = self.env["ai.extra.parameter"].create(
            {
                "name": "test_formula_param",
                "formula": "result = object.name",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )

        with self.assertRaises(ValidationError):
            param.formula = "import sys\nresult = sys.version"
            param.validate_parameter_formula()

    def test_formula_type_handling(self):
        test_cases = [
            ("result = 'string value'", str),
            ("result = 123", int),
            ("result = 45.67", float),
            ("result = True", bool),
            ("result = None", type(None)),
            ("result = {'key': 'value'}", dict),
            ("result = [1, 2, 3]", list),
        ]

        for formula, expected_type in test_cases:
            param = self.env["ai.extra.parameter"].create(
                {
                    "name": f"type_test_{expected_type.__name__}",
                    "formula": formula,
                    "parameter_type": "record",
                    "evaluate_type": "formula",
                }
            )
            result = param.evaluate_parameter(obj=self.partner)
            self.assertIsInstance(result, expected_type)

    def test_formula_with_odoo_recordset_methods(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "recordset_methods_formula",
                "formula": """result = {
    'child_count': len(object.child_ids),
    'has_children': bool(object.child_ids),
    'first_child': object.child_ids[0].name if object.child_ids else None,
    'mapped_names': object.child_ids.mapped('name'),
    'filtered_count': len(object.child_ids.filtered(lambda c: '@example.com' in c.email))
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner_with_children)
        self.assertEqual(result["child_count"], 2)
        self.assertTrue(result["has_children"])
        self.assertEqual(result["first_child"], "Child Company 1")
        self.assertEqual(result["mapped_names"], ["Child Company 1", "Child Company 2"])
        self.assertEqual(result["filtered_count"], 2)

    def test_expression_lambda_variables(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "lambda_expr",
                "expression": (
                    "Names: {', '.join(map(lambda x: x.upper(), object.name.split()))}"
                ),
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result, "Names: TEST, PARTNER")

        param2 = self.env["ai.extra.parameter"].create(
            {
                "name": "lambda_multi_expr",
                "expression": "{list(map(lambda x, y: x + y, [1, 2], [3, 4]))}",
                "parameter_type": "record",
                "evaluate_type": "expression",
            }
        )
        result2 = param2.evaluate_parameter(obj=self.partner)
        self.assertEqual(result2, "[4, 6]")

    def test_expression_function_def_not_allowed(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "func_def_expr",
                    "expression": "{(lambda: (def f(x): return x))()}",
                    "parameter_type": "record",
                    "evaluate_type": "expression",
                }
            )
        self.assertIn("Invalid Python syntax", str(cm.exception))

    def test_expression_exception_handler_not_allowed(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "except_expr",
                    "expression": "{try: 1/0 except Exception as e: 'error'}",
                    "parameter_type": "record",
                    "evaluate_type": "expression",
                }
            )
        self.assertIn("Invalid Python syntax", str(cm.exception))

    def test_expression_with_statement_not_allowed(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "with_expr",
                    "expression": "{with open('file') as f: f.read()}",
                    "parameter_type": "record",
                    "evaluate_type": "expression",
                }
            )
        self.assertIn("Invalid Python syntax", str(cm.exception))

    def test_formula_function_definition(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "func_def_formula",
                "formula": """def process_name(name):
    return name.upper() if name else 'N/A'

def get_length(s):
    return len(s) if s else 0

result = {
    'processed': process_name(object.name),
    'length': get_length(object.name)
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result["processed"], "TEST PARTNER")
        self.assertEqual(result["length"], 12)

    def test_formula_nested_function_closure_not_allowed(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "nested_func_formula",
                "formula": """def outer_func(prefix):
    def inner_func(name):
        return f"{prefix}: {name}"
    return inner_func

formatter = outer_func("Partner")
result = formatter(object.name)""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )

        with self.assertRaises(ValidationError) as cm:
            param.evaluate_parameter(obj=self.partner)
        self.assertIn("forbidden opcode", str(cm.exception))

    def test_formula_exception_handling(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "except_formula",
                "formula": """errors = []
data = []

try:
    data.append(object.name)
except AttributeError as e:
    errors.append(str(e))

try:
    x = 1 / 0
except ZeroDivisionError as err:
    errors.append("Division error caught")

try:
    y = object.non_existent_field
except Exception as ex:
    errors.append("Generic exception caught")

result = {
    'data': data,
    'error_count': len(errors),
    'has_errors': len(errors) > 0
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result["data"], ["Test Partner"])
        self.assertEqual(result["error_count"], 2)
        self.assertTrue(result["has_errors"])

    def test_formula_complex_variable_scoping(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "complex_scoping_formula",
                "formula": """global_var = "global"

def outer_function(param1):
    func_var = "function"

    def inner_function(param1, param2):
        inner_var = "inner"
        return f"{param1}-{param2}-{inner_var}"

    processor = lambda x: x.upper() if x else ""

    try:
        result_list = []
        for item in [param1, func_var]:
            result_list.append(processor(item))
    except Exception as e:
        result_list = ["error"]

    return {
        'inner_result': inner_function(param1, "test"),
        'processed': result_list
    }

output = outer_function(object.name)

names = [child.name for child in object.child_ids] if hasattr(object, 'child_ids') else []

result = {
    'function_output': output,
    'global_access': global_var,
    'names': names
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["global_access"], "global")
        self.assertEqual(
            result["function_output"]["inner_result"], "Test Partner-test-inner"
        )
        self.assertEqual(
            result["function_output"]["processed"], ["TEST PARTNER", "FUNCTION"]
        )

    def test_formula_undefined_var_in_function(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "undefined_in_func",
                    "formula": """def my_function():
    return undefined_variable + 1

result = my_function()""",
                    "parameter_type": "record",
                    "evaluate_type": "formula",
                }
            )
        self.assertIn("Undefined variables: undefined_variable", str(cm.exception))

    def test_formula_undefined_var_in_except(self):
        with self.assertRaises(ValidationError) as cm:
            self.env["ai.extra.parameter"].create(
                {
                    "name": "undefined_in_except",
                    "formula": """try:
    x = 1
except Exception as e:
    result = undefined_var""",
                    "parameter_type": "record",
                    "evaluate_type": "formula",
                }
            )
        self.assertIn("Undefined variables: undefined_var", str(cm.exception))

    def test_formula_lambda_already_tested_but_complex(self):
        param = self.env["ai.extra.parameter"].create(
            {
                "name": "complex_lambda_formula",
                "formula": """add_five = lambda x: x + 5

processors = [lambda x: x.upper(), lambda x: x.lower(), lambda x: x.title()]
test_string = object.name

combine = lambda a, b, c: f"{a}-{b}-{c}"

result = {
    'simple_lambda': add_five(10),
    'processed': [p(test_string) for p in processors],
    'combined': combine('A', 'B', 'C')
}""",
                "parameter_type": "record",
                "evaluate_type": "formula",
            }
        )
        result = param.evaluate_parameter(obj=self.partner)
        self.assertEqual(result["simple_lambda"], 15)
        self.assertEqual(
            result["processed"], ["TEST PARTNER", "test partner", "Test Partner"]
        )
        self.assertEqual(result["combined"], "A-B-C")
