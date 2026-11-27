# Developer Guide & Architecture

## Overview

The Orchestrator Engine coordinates conversations, QWeb prompt rendering, agent personas, tool selection, and asynchronous sub-task execution.

## Architecture Diagram (ASCII Art)

```
  +-------------------------------------------------------------------------+
  |                           ai_tool (OCA)                                 |
  |                        Base Tool Engine & @aitool                       |
  +------------------------------------v------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |                       ai_oca_native_agent                               |
  |             ai.prompt.template | ai.persona | ai.agent                  |
  +------------------------------------v------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |                    ai_oca_native_agent_tool                             |
  |              Bridge linking ai.agent to allowed ai.tool                 |
  +------------------------------------v------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |                    ai_oca_native_orchestrator                           |
  |      Execution engine, QWeb prompt rendering & task dispatching        |
  +-------------------------------------------------------------------------+
```

## How to Add New Capabilities (Developer Step-by-Step)

### 1. How to create a new `@aitool` on a model

Import `aitool` decorator from `odoo.addons.ai_tool.tools` and decorate a model method:

```python
from odoo import models
from odoo.addons.ai_tool.tools import aitool

class ResPartner(models.Model):
    _inherit = "res.partner"

    @aitool(
        input_schema={
            "partner_id": {"type": "integer", "description": "ID of partner to update"},
            "phone": {"type": "string", "description": "New phone number"},
        },
        required_inputs=["partner_id", "phone"],
        output_schema={"success": {"type": "boolean"}},
    )
    def _ai_update_partner_phone(self, partner_id, phone, **kwargs):
        partner = self.browse(partner_id)
        partner.write({"phone": phone})
        return {"success": True}
```

Then register the tool record in XML data:

```xml
<record model="ai.tool" id="tool_update_partner_phone">
    <field name="name">update_partner_phone</field>
    <field name="description">Update the phone number of a partner record.</field>
    <field name="model_id" ref="base.model_res_partner" />
    <field name="function_name">_ai_update_partner_phone</field>
    <field name="kind">generic</field>
</record>
```

### 2. How to create a custom Prompt Template and Persona

In XML data:

```xml
<record id="prompt_system_custom" model="ai.prompt.template">
    <field name="name">Custom System Prompt</field>
    <field name="code">system_custom</field>
    <field name="prompt_type">system</field>
    <field name="template_text"><![CDATA[<t>You are a specialized Assistant for <t t-out="company.name"/>.</t>]]></field>
</record>

<record id="persona_custom" model="ai.persona">
    <field name="name">Custom Persona</field>
    <field name="code">custom_persona</field>
    <field name="system_prompt_id" ref="prompt_system_custom" />
</record>
```

### 3. How to define an AI Agent and assign allowed tools

```xml
<record id="agent_custom" model="ai.agent">
    <field name="name">Custom Domain AI Agent</field>
    <field name="persona_id" ref="persona_custom" />
    <field name="execution_mode">user_context</field>
    <field name="tool_ids" eval="[(6, 0, [ref('tool_update_partner_phone'), ref('ai_tool.current_date')])]" />
</record>
```
