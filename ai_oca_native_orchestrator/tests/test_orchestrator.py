# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
from unittest.mock import patch

from odoo import Command
from odoo.tests.common import TransactionCase


class TestAiOrchestrator(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.system_prompt = cls.env.ref(
            "ai_oca_native_orchestrator.prompt_system_default"
        )
        cls.user_wrapper = cls.env.ref(
            "ai_oca_native_orchestrator.prompt_user_wrapper_default"
        )
        cls.persona = cls.env.ref("ai_oca_native_orchestrator.persona_default")
        cls.partner = cls.env["res.partner"].create({"name": "Test Partner"})
        cls.thread = cls.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": cls.partner.id,
                "name": "New Thread",
            }
        )

    def setUp(self):
        super().setUp()
        self.partner = self.partner.with_env(self.env)
        self.thread = self.thread.with_env(self.env)
        self.system_prompt = self.env.ref(
            "ai_oca_native_orchestrator.prompt_system_default"
        )
        self.system_prompt.template_text = (
            "<t>You are an autonomous Odoo AI Agent.\n"
            "Your goal is to understand the user's intent, plan necessary actions, "
            "coordinate specialized sub-agents when required, "
            "and provide clear and helpful responses.\n"
            "Preferred language: <t t-out=\"user.partner_id.lang or 'en_US'\"/>.</t>"
        )
        self.user_wrapper = self.env.ref(
            "ai_oca_native_orchestrator.prompt_user_wrapper_default"
        )
        self.user_wrapper.template_text = (
            '<t><t t-if="record">Context Record: <t t-out="res_model"/>'
            '<t t-if="record.display_name"> (<t t-out="record.display_name"/>)</t>\n'
            '</t><t t-if="record_context">Record Data:\n'
            '<t t-out="record_context"/>\n'
            '</t><t t-if="chatter_messages">Chatter History:\n'
            '<t t-out="chatter_messages"/>\n'
            '</t><t t-if="task_threads">Sub-agent Execution History:\n'
            '<t t-out="task_threads"/>\n'
            "</t>User Request:\n"
            '<t t-out="content"/></t>'
        )
        self.persona = self.env.ref("ai_oca_native_orchestrator.persona_default")
        self.env["ai.persona"].search([]).write({"is_default": False})
        self.persona.is_default = True
        self.persona.system_prompt_id = self.system_prompt
        self.persona.user_wrapper_prompt_id = self.user_wrapper
        decide_patcher = patch(
            "odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.decide_choice",
            return_value={
                "name": "next_action",
                "type": "choice",
                "choice": "done",
                "confidence": 0.99,
                "probabilities": [],
            },
        )
        self.mock_decide_choice = decide_patcher.start()
        self.addCleanup(decide_patcher.stop)

    def test_prompt_template_qweb_render(self):
        template = self.env["ai.prompt.template"].create(
            {
                "name": "Custom Test Prompt",
                "code": "test_prompt",
                "prompt_type": "system",
                "template_text": (
                    "<t>Hello <t t-out='user.name'/> on <t t-out='res_model'/> for "
                    "<t t-out='record.name'/> in company <t t-out='company.name'/>!</t>"
                ),
            }
        )
        # Passing 'record' auto-populates 'res_model', 'user', 'company', 'record'
        rendered = template.render(record=self.partner)
        self.assertIn(self.env.user.name, rendered)
        self.assertIn("res.partner", rendered)
        self.assertIn("Test Partner", rendered)
        self.assertIn(self.env.company.name, rendered)

    def test_default_system_prompt_renders_record_display_name(self):
        default_prompt = self.env.ref(
            "ai_oca_native_orchestrator.prompt_system_default"
        )
        default_prompt.template_text = (
            "<t>You are an autonomous Odoo AI Agent.\n"
            'The user <t t-out="user.name"/> is looking at '
            '<t t-out="res_model"/>'
            '<t t-if="record"> (<t t-out="record.display_name"/>)</t>.\n'
            "Preferred language: <t t-out=\"user.partner_id.lang or 'en_US'\"/>.</t>"
        )
        rendered = default_prompt.render(record=self.partner)
        self.assertIn("(Test Partner)", rendered)

    def test_prompt_template_plain_text(self):
        # Test template string NOT starting with '<'
        plain_template = self.env["ai.prompt.template"].create(
            {
                "name": "Plain Text Prompt",
                "code": "plain_text_prompt",
                "prompt_type": "system",
                "template_text": "Hello plain text user!",
            }
        )
        rendered = plain_template.render()
        self.assertEqual(rendered, "Hello plain text user!")

    def test_prompt_template_record_context_and_fallback(self):
        template = self.env["ai.prompt.template"].create(
            {
                "name": "Record Prompt",
                "code": "record_prompt",
                "prompt_type": "system",
                "template_text": (
                    "<t>Hello <t t-out='record.name'/>: '<t t-out='content'/>'!</t>"
                ),
            }
        )
        empty_template = self.env["ai.prompt.template"].create(
            {
                "name": "Empty Prompt",
                "code": "empty_prompt",
                "prompt_type": "system",
                "template_text": "  ",
            }
        )
        self.assertEqual(empty_template.render(), "")

        # Passing 'record' and content
        rendered_rec = template.render(content="My Request", record=self.partner)
        self.assertEqual(rendered_rec, "Hello Test Partner: 'My Request'!")

        # Malformed QWeb template triggers exception fallback to format()
        fallback_template = self.env["ai.prompt.template"].create(
            {
                "name": "Fallback Prompt",
                "code": "fallback_prompt",
                "prompt_type": "system",
                "template_text": "<t t-out='invalid_expr.foo'/>Hello {user_name}!",
            }
        )
        rendered_fallback = fallback_template.render(user_name="World")
        self.assertIn("Hello World!", rendered_fallback)

        # Unformattable broken string fallback
        raw_fallback_template = self.env["ai.prompt.template"].create(
            {
                "name": "Raw Fallback Prompt",
                "code": "raw_fallback_prompt",
                "prompt_type": "system",
                "template_text": (
                    "<t t-out='invalid_expr.foo'/>Hello {invalid_format_key}!"
                ),
            }
        )
        rendered_raw = raw_fallback_template.render()
        self.assertIn("Hello {invalid_format_key}!", rendered_raw)

    def test_prompt_template_render_values_defaults_without_record(self):
        template = self.env["ai.prompt.template"].create(
            {
                "name": "Default Keys Test Prompt",
                "code": "default_keys_prompt",
                "prompt_type": "system",
                "template_text": (
                    "<t>User: <t t-out='user.name'/>, Model: '<t t-out='res_model'/>'"
                    "<t t-if='record_context'> Context: <t t-out='record_context'/></t>"
                    "<t t-if='record_chatter'> Chatter: <t t-out='record_chatter'/></t>"
                    "<t t-if='task_threads'> Tasks: <t t-out='task_threads'/></t></t>"
                ),
            }
        )
        # Rendering with no record should NOT raise NameError
        rendered = template.render()
        self.assertIn("User:", rendered)
        self.assertIn("Model: ''", rendered)
        self.assertNotIn("Context:", rendered)
        self.assertNotIn("Chatter:", rendered)
        self.assertNotIn("Tasks:", rendered)

    def test_prompt_template_context_flags_toggling(self):
        # Disabled record_data and record_chatter
        template_disabled = self.env["ai.prompt.template"].create(
            {
                "name": "Flags Disabled Prompt",
                "code": "flags_disabled_prompt",
                "prompt_type": "system",
                "include_record_data": False,
                "include_record_chatter": False,
                "template_text": (
                    "<t>Data: <t t-out='record_context or \"none\"'/>, "
                    "Chatter: <t t-out='record_chatter or \"none\"'/></t>"
                ),
            }
        )
        rendered_disabled = template_disabled.render(record=self.partner)
        self.assertEqual(rendered_disabled, "Data: none, Chatter: none")

        # Enabled record_data and record_chatter
        template_enabled = self.env["ai.prompt.template"].create(
            {
                "name": "Flags Enabled Prompt",
                "code": "flags_enabled_prompt",
                "prompt_type": "system",
                "include_record_data": True,
                "include_record_chatter": True,
                "template_text": (
                    "<t><t t-if='record_context'>"
                    "HasData: <t t-out='record_context'/></t>"
                    "<t t-if='record_chatter'>HasChatter</t></t>"
                ),
            }
        )
        with patch(
            "odoo.addons.ai_oca_native_agent.models.ai_prompt_template.json_default",
            side_effect=TypeError("Mock non-serializable"),
        ):
            rendered_enabled = template_enabled.render(record=self.partner)
        self.assertIn("HasData:", rendered_enabled)

    def test_persona_creation(self):
        template = self.env["ai.prompt.template"].create(
            {
                "name": "Persona Prompt",
                "code": "persona_prompt",
                "prompt_type": "system",
                "template_text": "Persona template",
            }
        )
        persona = self.env["ai.persona"].create(
            {
                "name": "Support Agent",
                "code": "support_agent",
                "system_prompt_id": template.id,
                "description": "Customer Support Persona",
            }
        )
        self.assertEqual(persona.system_prompt_id.id, template.id)

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_process_assistant_message(self, mock_chat):
        mock_chat.return_value = "I can help you update partner information."

        self.thread._add_message("Help me update partner information", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )

        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "done")
        self.assertEqual(
            assistant_msg.content, "I can help you update partner information."
        )

        # Verify task thread message tracking
        task_threads = assistant_msg.task_thread_ids
        self.assertTrue(task_threads)
        task_thread = task_threads[0]
        self.assertEqual(task_thread.name, "Orchestrator Execution")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_preserve_existing_thread_title(self, mock_chat):
        mock_chat.return_value = "Sure, here is your answer."

        custom_thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "Custom Fixed Title",
            }
        )
        custom_thread._add_message("Follow-up question", role="user")
        assistant_msg = custom_thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(custom_thread.name, "Custom Fixed Title")

    def test_orchestrator_process_assistant_message_cancelled(self):
        assistant_msg = self.thread._add_message("", role="assistant", status="cancel")
        result = assistant_msg._process_assistant_message()
        self.assertIsNone(result)

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_process_assistant_message_empty_llm_response(self, mock_chat):
        mock_chat.return_value = None

        self.thread._add_message("Help me update partner information", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "cancel")
        self.assertEqual(assistant_msg.content, "Failed to get a response from LLM.")

    def test_get_orchestrator_system_prompt(self):
        assistant_msg = self.thread._add_message("", role="assistant")
        sys_prompt = assistant_msg._get_orchestrator_system_prompt()
        self.assertTrue(sys_prompt)
        self.assertEqual(sys_prompt[0]["role"], "system")
        self.assertIn("autonomous Odoo AI Agent", sys_prompt[0]["content"])

    def test_get_orchestrator_llm_messages_contextualization(self):
        # Empty thread returns system messages
        empty_thread = self.env["ai.thread"].create(
            {
                "name": "Empty Thread",
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        empty_assistant = empty_thread._add_message("", role="assistant")
        self.assertEqual(len(empty_assistant._get_orchestrator_llm_messages()), 1)

        # Multi-turn history with contextualized latest user request
        thread = self.env["ai.thread"].create(
            {
                "name": "Multi Turn Thread",
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        thread._add_message("Past message 1", role="user")
        thread._add_message("Past assistant response", role="assistant", status="done")
        thread._add_message("Latest user question", role="user")
        assistant_msg = thread._add_message("", role="assistant", status="processing")

        llm_messages = assistant_msg._get_orchestrator_llm_messages()
        # system + user1 + assistant + user2(contextualized)
        self.assertEqual(len(llm_messages), 4)
        self.assertEqual(llm_messages[0]["role"], "system")
        self.assertEqual(llm_messages[1]["role"], "user")
        self.assertEqual(llm_messages[1]["content"], "Past message 1")
        self.assertEqual(llm_messages[2]["role"], "assistant")
        self.assertEqual(llm_messages[2]["content"], "Past assistant response")
        self.assertEqual(llm_messages[3]["role"], "user")
        self.assertIn("Test Partner", llm_messages[3]["content"])
        self.assertIn("Latest user question", llm_messages[3]["content"])

        # Test when persona has no user wrapper
        persona = self.env["ai.persona"].search([("is_default", "=", True)], limit=1)
        persona.user_wrapper_prompt_id = False
        raw_llm_messages = assistant_msg._get_orchestrator_llm_messages()
        self.assertEqual(raw_llm_messages[3]["content"], "Latest user question")

        # Test when user wrapper returns empty rendered string
        empty_wrapper = self.env["ai.prompt.template"].create(
            {
                "name": "Empty Wrapper",
                "code": "empty_wrapper",
                "prompt_type": "user_wrapper",
                "template_text": " ",
            }
        )
        persona.user_wrapper_prompt_id = empty_wrapper
        empty_wrap_llm_messages = assistant_msg._get_orchestrator_llm_messages()
        self.assertEqual(empty_wrap_llm_messages[3]["content"], "Latest user question")

    def test_fast_thread_title_generation(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "New Thread",
            }
        )
        thread._add_message("What is the total revenue for this partner?", role="user")
        with patch.object(
            type(self.env["ai.llm.client"]),
            "chat",
            return_value="Partner Revenue Overview",
        ):
            thread._action_generate_thread_title()
            self.assertEqual(thread.name, "Partner Revenue Overview")

    def test_fast_thread_title_generation_no_template_fallback(self):
        self.env["ai.prompt.template"].search(
            [("prompt_type", "=", "thread_title")]
        ).unlink()
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "New Thread",
            }
        )
        thread._add_message("What is the total revenue for this partner?", role="user")
        with patch.object(
            type(self.env["ai.llm.client"]),
            "chat",
            return_value="Partner Revenue Overview",
        ):
            thread._action_generate_thread_title()
            self.assertEqual(thread.name, "Partner Revenue Overview")

    def test_fast_thread_title_generation_empty_llm_result(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "New Thread",
            }
        )
        thread._add_message("What is the total revenue for this partner?", role="user")
        with patch.object(
            type(self.env["ai.llm.client"]),
            "chat",
            return_value="   ",
        ):
            thread._action_generate_thread_title()
            self.assertIn("What is the total revenue", thread.name)

    def test_fast_thread_title_generation_early_returns(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "Existing Custom Title",
            }
        )
        thread._add_message("Test question", role="user")
        thread._action_generate_thread_title()
        self.assertEqual(thread.name, "Existing Custom Title")

        thread2 = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "New Thread",
            }
        )
        thread2._action_generate_thread_title()
        self.assertEqual(thread2.name, "New Thread")

        thread3 = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "New Thread",
            }
        )
        thread3._add_message("", role="user")
        thread3._action_generate_thread_title()
        self.assertEqual(thread3.name, "New Thread")

    def test_fast_thread_title_generation_exception_fallback(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "New Thread",
            }
        )
        thread._add_message("What is the total revenue for this partner?", role="user")
        with patch.object(
            type(self.env["ai.llm.client"]),
            "chat",
            side_effect=Exception("LLM Error"),
        ):
            thread._action_generate_thread_title()
            self.assertIn("What is the total revenue", thread.name)

    def test_get_orchestrator_system_prompt_empty_persona_rendered(self):
        empty_prompt = self.env["ai.prompt.template"].create(
            {"name": "Empty Prompt", "code": "empty_prompt", "template_text": ""}
        )
        persona = self.env["ai.persona"].search([("is_default", "=", True)], limit=1)
        persona.system_prompt_id = empty_prompt
        assistant_msg = self.thread._add_message("", role="assistant")
        sys_prompt = assistant_msg._get_orchestrator_system_prompt()
        self.assertTrue(sys_prompt)
        self.assertEqual(sys_prompt[0]["role"], "system")
        self.assertIn("helpful Odoo Assistant", sys_prompt[0]["content"])

    def test_prompt_template_prefilled_render_values(self):
        template = self.env["ai.prompt.template"].create(
            {
                "name": "Prefilled Template",
                "code": "prefilled_prompt",
                "template_text": (
                    "Context: <t t-out='record_context'/> "
                    "Chatter: <t t-out='record_chatter'/>"
                ),
            }
        )
        res = template.render(
            record=self.partner,
            res_model="res.partner",
            res_id=999,
            record_context="CUSTOM_CTX",
            record_chatter="CUSTOM_CHATTER",
        )
        self.assertIn("CUSTOM_CTX", res)
        self.assertIn("CUSTOM_CHATTER", res)

    def test_get_orchestrator_system_prompt_no_system_prompt_id(self):
        persona = self.env["ai.persona"].search([("is_default", "=", True)], limit=1)
        persona.system_prompt_id = False
        assistant_msg = self.thread._add_message("", role="assistant")
        sys_prompt = assistant_msg._get_orchestrator_system_prompt()
        self.assertTrue(sys_prompt)
        self.assertIn("helpful Odoo Assistant", sys_prompt[0]["content"])

    def test_get_orchestrator_persona_fallback_default_persona(self):
        thread_no_agent = self.env["ai.thread"].create(
            {
                "name": "No Agent Thread",
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "agent_id": False,
            }
        )
        msg = self.env["ai.message"].create(
            {
                "thread_id": thread_no_agent.id,
                "role": "user",
                "content": "Hello",
            }
        )
        persona = msg._get_orchestrator_persona()
        self.assertEqual(
            persona, self.env.ref("ai_oca_native_orchestrator.persona_default")
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_fast_path_direct_response(self, mock_chat):
        self.mock_decide_choice.return_value = {
            "name": "next_action",
            "type": "choice",
            "choice": "done",
            "confidence": 0.98,
        }
        mock_chat.return_value = "Bonjour ! En quoi puis-je vous aider ?"

        self.thread._add_message("Bonjour", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "done")
        self.assertEqual(
            assistant_msg.content, "Bonjour ! En quoi puis-je vous aider ?"
        )
        self.assertFalse(assistant_msg.payload)
        self.mock_decide_choice.assert_called_once()

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_zero_arg_tool_direct_execution_via_system_one(
        self, mock_chat
    ):
        self.mock_decide_choice.side_effect = [
            {"name": "next_action", "type": "choice", "choice": "get_date"},
            {"name": "next_action", "type": "choice", "choice": "done"},
        ]
        mock_chat.return_value = "Nous sommes aujourd'hui."

        self.thread._add_message("Quelle est la date ?", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "done")
        self.assertEqual(assistant_msg.content, "Nous sommes aujourd'hui.")
        # System 2 chat() is called only ONCE for the final synthesis (not for get_date!)
        self.assertEqual(mock_chat.call_count, 1)
        tool_messages = assistant_msg.task_thread_ids[0].task_message_ids.filtered(
            lambda m: m.role == "tool"
        )
        self.assertTrue(tool_messages)
        self.assertIn("date", tool_messages[0].payload)

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_direct_tool_calling(self, mock_chat):
        self.mock_decide_choice.side_effect = [
            {
                "name": "next_action",
                "type": "choice",
                "choice": "agent_list_available_agents",
            },
            {"name": "next_action", "type": "choice", "choice": "done"},
        ]
        mock_chat.side_effect = [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_agent_list",
                        "type": "function",
                        "function": {
                            "name": "agent_list_available_agents",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            "Il y a des agents actifs configurés dans Odoo.",
        ]

        self.thread._add_message("Quels agents sont disponibles ?", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "done")
        self.assertEqual(
            assistant_msg.content, "Il y a des agents actifs configurés dans Odoo."
        )
        self.assertEqual(mock_chat.call_count, 2)
        first_call_kwargs = mock_chat.call_args_list[0].kwargs
        self.assertEqual(len(first_call_kwargs["tools"]), 1)
        self.assertEqual(
            first_call_kwargs["tools"][0]["function"]["name"],
            "agent_list_available_agents",
        )
        self.assertEqual(
            first_call_kwargs["tool_choice"],
            {
                "type": "function",
                "function": {"name": "agent_list_available_agents"},
            },
        )

        task_threads = assistant_msg.task_thread_ids
        self.assertTrue(task_threads)
        messages = task_threads[0].task_message_ids
        tool_messages = messages.filtered(lambda m: m.role == "tool")
        self.assertTrue(tool_messages)
        self.assertIn("agents", tool_messages[0].payload)

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_action_plan_proposal(self, mock_chat):
        self.mock_decide_choice.return_value = {
            "name": "next_action",
            "type": "choice",
            "choice": "agent_propose_action_plan",
        }
        plan_args = {
            "summary": "Plan de requalification CRM",
            "steps": [
                {
                    "step_id": 1,
                    "objective": "Lister les leads froids",
                    "target_type": "tool",
                    "target_name": "agent_list_available_tools",
                    "params": {},
                    "depends_on": [],
                },
                {
                    "step_id": 2,
                    "objective": "Assigner les opportunités",
                    "target_type": "agent",
                    "target_name": "Sales Agent",
                    "params": {},
                    "depends_on": [1],
                },
            ],
        }
        mock_chat.return_value = {
            "content": "J'ai préparé un plan de requalification.",
            "tool_calls": [
                {
                    "id": "call_plan_1",
                    "type": "function",
                    "function": {
                        "name": "agent_propose_action_plan",
                        "arguments": json.dumps(plan_args),
                    },
                }
            ],
        }

        self.thread._add_message(
            "Requalifie les leads froids avec l'équipe de vente.", role="user"
        )
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "awaiting_approval")
        self.assertTrue(assistant_msg.payload)
        self.assertEqual(
            assistant_msg.payload.get("summary"), "Plan de requalification CRM"
        )
        self.assertEqual(len(assistant_msg.payload.get("steps")), 2)
        self.assertEqual(
            assistant_msg.content, "J'ai préparé un plan de requalification."
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_action_plan_proposal_without_content_fallback(
        self, mock_chat
    ):
        self.mock_decide_choice.return_value = {
            "name": "next_action",
            "type": "choice",
            "choice": "agent_propose_action_plan",
        }
        plan_args = {
            "summary": "Plan d'archivage",
            "steps": [
                {
                    "step_id": 1,
                    "objective": "Archiver les vieux leads",
                    "target_type": "tool",
                    "target_name": "agent_list_available_tools",
                }
            ],
        }
        mock_chat.return_value = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_plan_2",
                    "type": "function",
                    "function": {
                        "name": "agent_propose_action_plan",
                        "arguments": json.dumps(plan_args),
                    },
                }
            ],
        }

        self.thread._add_message("Archive les vieux leads", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "awaiting_approval")
        self.assertIn("### Action Plan: Plan d'archivage", assistant_msg.content)
        self.assertIn("Step 1: Archiver les vieux leads", assistant_msg.content)

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_action_plan_proposal_invalid_args_fallback(self, mock_chat):
        self.mock_decide_choice.side_effect = [
            {
                "name": "next_action",
                "type": "choice",
                "choice": "agent_propose_action_plan",
            },
            {"name": "next_action", "type": "choice", "choice": "done"},
        ]
        mock_chat.side_effect = [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_plan_err",
                        "type": "function",
                        "function": {
                            "name": "agent_propose_action_plan",
                            "arguments": '{"invalid": "schema"}',
                        },
                    }
                ],
            },
            "Impossible de valider le plan proposé.",
        ]

        self.thread._add_message("Action invalide", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "done")
        self.assertEqual(
            assistant_msg.content, "Impossible de valider le plan proposé."
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_tool_execution_error_handling(self, mock_chat):
        self.mock_decide_choice.side_effect = [
            {
                "name": "next_action",
                "type": "choice",
                "choice": "agent_list_available_tools",
            },
            {"name": "next_action", "type": "choice", "choice": "done"},
        ]
        mock_chat.side_effect = [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_bad_tool",
                        "type": "function",
                        "function": {
                            "name": "non_existent_tool",
                            "arguments": "{bad-json",
                        },
                    }
                ],
            },
            "Désolé, cet outil n'est pas disponible.",
        ]

        self.thread._add_message("Lance un outil inconnu", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "done")
        self.assertEqual(
            assistant_msg.content, "Désolé, cet outil n'est pas disponible."
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_tool_execution_with_dict_args(self, mock_chat):
        self.mock_decide_choice.side_effect = [
            {
                "name": "next_action",
                "type": "choice",
                "choice": "agent_list_available_tools",
            },
            {"name": "next_action", "type": "choice", "choice": "done"},
        ]
        mock_chat.side_effect = [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_dict_args",
                        "type": "function",
                        "function": {
                            "name": "agent_list_available_tools",
                            "arguments": {"res_model": "res.partner"},
                        },
                    }
                ],
            },
            "Voici les outils pour res.partner.",
        ]

        self.thread._add_message("Liste les outils partner", role="user")
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        assistant_msg._action_extract_intent()

        self.assertEqual(assistant_msg.status, "done")
        self.assertEqual(assistant_msg.content, "Voici les outils pour res.partner.")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_parameterized_tool_chat_fallback_branches(self, mock_chat):
        self.mock_decide_choice.return_value = {
            "name": "next_action",
            "type": "choice",
            "choice": "agent_list_available_tools",
        }
        mock_chat.side_effect = [
            None,
            "String fallback response",
            {"content": "Dict without tool_calls fallback", "tool_calls": []},
        ]

        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        task_thread = assistant_msg._create_orchestrator_task_thread()

        self.assertIsNone(assistant_msg._orchestrate_assistant_response(task_thread))
        self.assertEqual(
            assistant_msg._orchestrate_assistant_response(task_thread),
            "String fallback response",
        )
        self.assertEqual(
            assistant_msg._orchestrate_assistant_response(task_thread),
            "Dict without tool_calls fallback",
        )

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_react_loop_max_iterations(self, mock_chat):
        self.mock_decide_choice.return_value = {
            "name": "next_action",
            "type": "choice",
            "choice": "agent_list_available_agents",
        }
        mock_chat.return_value = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_loop",
                    "type": "function",
                    "function": {
                        "name": "agent_list_available_agents",
                        "arguments": "{}",
                    },
                }
            ],
        }

        task_thread = self.thread._add_message(
            "Boucle", role="user"
        )._create_orchestrator_task_thread()
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        result = assistant_msg._orchestrate_assistant_response(
            task_thread, max_iterations=2
        )
        self.assertEqual(result, "Maximum reasoning iterations reached.")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_orchestrator_response_without_tools(self, mock_chat):
        mock_chat.return_value = "Direct answer without tools"

        agent_no_tools = self.env["ai.agent"].create(
            {
                "name": "Agent No Tools",
                "user_id": self.env.ref(
                    "ai_oca_native_orchestrator.user_ai_orchestrator_agent"
                ).id,
                "execution_mode": "user_context",
                "tool_ids": [Command.clear()],
            }
        )

        thread_no_tools = self.env["ai.thread"].create(
            {
                "name": "No Tools Thread",
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "agent_id": agent_no_tools.id,
            }
        )
        assistant_msg = thread_no_tools._add_message(
            "", role="assistant", status="processing"
        )
        task_thread = assistant_msg._create_orchestrator_task_thread()
        result = assistant_msg._orchestrate_assistant_response(task_thread)
        self.assertEqual(result, "Direct answer without tools")

    def test_get_orchestrator_agent_fallback_to_default(self):
        thread = self.env["ai.thread"].create(
            {
                "name": "No Agent Assigned",
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "agent_id": False,
            }
        )
        msg = thread._add_message("Test", role="user")
        agent = msg._get_orchestrator_agent()
        self.assertEqual(
            agent,
            self.env.ref("ai_oca_native_orchestrator.default_main_orchestrator_agent"),
        )
