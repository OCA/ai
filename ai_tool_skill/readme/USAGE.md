To define a new AI skill in XML, create a record of model `ai.skill`:

```xml
<odoo>
    <record model="ai.skill" id="skill_example">
        <field name="name">Example Skill Guide</field>
        <field name="description">Guidelines for performing a specific operation.</field>
        <field name="content"><![CDATA[# Example Skill Guide

1. Search for records using specific domain filters.
2. Verify record values before performing updates.
]]></field>
    </record>
</odoo>
```

When an `ai.skill` record is created:
- An underlying `ai.tool` record is automatically generated via delegation.
- Executing the tool returns a dictionary containing the skill `name` and Markdown `content`.
- AI Agents can preload skills into their System Prompt or invoke them as tools on demand.
