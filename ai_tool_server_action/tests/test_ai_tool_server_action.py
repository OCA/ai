# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestAiToolServerAction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server_action = cls.env["ir.actions.server"].create(
            {
                "name": "Test Server Action",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": """
args = env.context.get('tool_args', {})
action = {
    'received_query': args.get('query'),
    'status': 'ok'
}
""",
            }
        )
        cls.ai_tool = cls.env["ai.tool"].create(
            {
                "name": "test_server_action_tool",
                "description": "Test tool description",
                "kind": "server_action",
                "server_action_id": cls.server_action.id,
                "input_schema_json": (
                    '{"type": "object", "properties": {"query": {"type": "string"}}}'
                ),
                "output_schema_json": '{"type": "object"}',
            }
        )

    def test_tool_creation(self):
        """Test that the tool is correctly created without model_id and function_name"""
        self.assertEqual(self.ai_tool.kind, "server_action")
        self.assertEqual(self.ai_tool.server_action_id, self.server_action)
        self.assertFalse(self.ai_tool.model_id)
        self.assertFalse(self.ai_tool.function_name)

    def test_get_tool_definition(self):
        """Test that _get_tool_definition correctly parses JSON schemas"""
        definition = self.ai_tool._get_tool_definition()
        self.assertEqual(definition["name"], "test_server_action_tool")
        self.assertEqual(definition["description"], "Test tool description")
        self.assertEqual(
            definition["inputSchema"],
            {"type": "object", "properties": {"query": {"type": "string"}}},
        )
        self.assertEqual(definition["outputSchema"], {"type": "object"})

    def test_get_tool_definition_invalid_json(self):
        """Test that _get_tool_definition handles invalid JSON gracefully"""
        self.ai_tool.write(
            {
                "input_schema_json": "invalid json",
                "output_schema_json": "also invalid",
            }
        )
        definition = self.ai_tool._get_tool_definition()
        self.assertEqual(definition["inputSchema"], {})
        self.assertEqual(definition["outputSchema"], {})

    def test_execute_tool(self):
        """Test that _execute_tool correctly delegates to the server action"""
        result = self.ai_tool._execute_tool(query="test_query")
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("received_query"), "test_query")

    def test_execute_tool_no_dict_return(self):
        """Test that _execute_tool handles server actions that do not return a dict"""
        server_action_empty = self.env["ir.actions.server"].create(
            {
                "name": "Empty Server Action",
                "model_id": self.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": "action = False",
            }
        )
        self.ai_tool.server_action_id = server_action_empty
        result = self.ai_tool._execute_tool()
        self.assertEqual(
            result, {"status": "success", "message": "Action executed successfully"}
        )

    def test_execute_tool_ui_action(self):
        """Test that UI actions are intercepted and return a success message"""
        server_action_ui = self.env["ir.actions.server"].create(
            {
                "name": "UI Server Action",
                "model_id": self.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": "action = {'type': 'ir.actions.act_window', 'name': 'Test'}",
            }
        )
        self.ai_tool.server_action_id = server_action_ui
        result = self.ai_tool._execute_tool()
        self.assertEqual(
            result,
            {
                "status": "success",
                "message": "Action executed successfully (UI action ignored)",
            },
        )

    def test_ir_actions_server_ai_tool_id(self):
        """Test the computed fields on ir.actions.server"""
        self.assertEqual(self.server_action.ai_tool_id, self.ai_tool)
        self.assertEqual(
            self.server_action.input_schema_json, self.ai_tool.input_schema_json
        )
        self.assertEqual(
            self.server_action.output_schema_json, self.ai_tool.output_schema_json
        )

    def test_action_open_ai_tool_wizard(self):
        """Test the button action returns correct dictionary"""
        action = self.server_action.action_open_ai_tool_wizard()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "ai.tool.server.action.wizard")
        self.assertEqual(
            action["context"]["default_server_action_id"], self.server_action.id
        )

    def test_wizard_default_get_existing(self):
        """Test wizard default_get when ai_tool already exists"""
        wizard_vals = (
            self.env["ai.tool.server.action.wizard"]
            .with_context(default_server_action_id=self.server_action.id)
            .default_get(
                [
                    "server_action_id",
                    "ai_tool_id",
                    "name",
                    "description",
                    "input_schema_json",
                    "output_schema_json",
                ]
            )
        )
        self.assertEqual(wizard_vals["ai_tool_id"], self.ai_tool.id)
        self.assertEqual(wizard_vals["name"], self.ai_tool.name)
        self.assertEqual(wizard_vals["description"], self.ai_tool.description)

    def test_wizard_default_get_new(self):
        """Test wizard default_get when ai_tool does not exist"""
        new_action = self.env["ir.actions.server"].create(
            {
                "name": "New Action",
                "model_id": self.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": "action = False",
            }
        )
        wizard_vals = (
            self.env["ai.tool.server.action.wizard"]
            .with_context(default_server_action_id=new_action.id)
            .default_get(["server_action_id", "name"])
        )
        self.assertFalse(wizard_vals.get("ai_tool_id"))
        self.assertEqual(wizard_vals["name"], "New Action")

    def test_wizard_action_apply_create(self):
        """Test wizard creating a new ai.tool"""
        new_action = self.env["ir.actions.server"].create(
            {
                "name": "New Action 2",
                "model_id": self.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": "action = False",
            }
        )
        wizard = (
            self.env["ai.tool.server.action.wizard"]
            .with_context(default_server_action_id=new_action.id)
            .create(
                {
                    "server_action_id": new_action.id,
                    "name": "New Tool",
                    "description": "Desc",
                    "input_schema_json": "{}",
                    "output_schema_json": "{}",
                }
            )
        )
        wizard.action_apply()
        self.assertTrue(new_action.ai_tool_id)
        self.assertEqual(new_action.ai_tool_id.name, "New Tool")

    def test_wizard_action_apply_update(self):
        """Test wizard updating an existing ai.tool"""
        wizard = (
            self.env["ai.tool.server.action.wizard"]
            .with_context(default_server_action_id=self.server_action.id)
            .create(
                {
                    "server_action_id": self.server_action.id,
                    "ai_tool_id": self.ai_tool.id,
                    "name": "Updated Tool",
                    "description": "Updated Desc",
                    "input_schema_json": '{"test": 1}',
                }
            )
        )
        wizard.action_apply()
        self.assertEqual(self.ai_tool.name, "Updated Tool")
        self.assertEqual(self.ai_tool.description, "Updated Desc")
        self.assertEqual(self.ai_tool.input_schema_json, '{"test": 1}')

    def test_ir_actions_server_inverse_fields(self):
        """Test that writing fields updates the underlying ai.tool"""
        self.server_action.write(
            {
                "ai_tool_description": "New inverse description",
                "input_schema_json": '{"type": "object"}',
                "output_schema_json": '{"type": "string"}',
            }
        )
        self.assertEqual(self.ai_tool.description, "New inverse description")
        self.assertEqual(self.ai_tool.input_schema_json, '{"type": "object"}')
        self.assertEqual(self.ai_tool.output_schema_json, '{"type": "string"}')

    def test_execute_tool_super(self):
        """Test that _execute_tool handles non-server-action tools via super()"""
        generic_tool = self.env["ai.tool"].create(
            {
                "name": "get_date_tool",
                "description": "Get current date",
                "kind": "generic",
                "model_id": self.env.ref("ai_tool.model_ai_tool").id,
                "function_name": "_ai_get_date",
            }
        )
        result = generic_tool._execute_tool()
        self.assertIn("date", result)

    def test_get_tool_definition_super(self):
        """Test that _get_tool_definition handles non-server-action tools via super()"""
        generic_tool = self.env["ai.tool"].create(
            {
                "name": "get_date_tool",
                "description": "Get current date",
                "kind": "generic",
                "model_id": self.env.ref("ai_tool.model_ai_tool").id,
                "function_name": "_ai_get_date",
            }
        )
        definition = generic_tool._get_tool_definition()
        self.assertEqual(definition["name"], "get_date_tool")
        self.assertIn("date", definition["outputSchema"].get("properties", {}))
