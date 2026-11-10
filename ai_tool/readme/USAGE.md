Tools are managed under `Settings > Technical > AI > AI Tool` (developer mode).
End users normally interact with tools through integration modules such as
`ai_oca_mcp`; this addon only provides the registry and the definition API.

## Defining a tool in a glue module

Example: a `total_sale_order` tool that returns the total sales amount within a
date range, optionally for a specific customer.

```xml
<odoo>
    <record model="ai.tool" id="total_sale_order_tool">
        <field name="name">total_sale_order</field>
        <field
            name="description"
        >Calculate the total amount of sale orders within a date range and optionally for a specific customer.</field>
        <field name="model_id" ref="model_sale_order" />
        <field name="function_name">_ai_total_sale_order</field>
        <field name="kind">generic</field>
    </record>
</odoo>
```

```python
from odoo import models
from odoo.addons.ai_tool.tools import aitool


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @aitool(
        input_schema={
            "start_date": {"type": "date"},
            "end_date": {"type": "date"},
            "customer_id": {"type": "integer"},
        },
        required_inputs=["start_date", "end_date"],
        output_schema={
            "amount_total": {"type": "number"},
        },
    )
    def _ai_total_sale_order(self, start_date, end_date, customer_id=None):
        domain = [("date_order", ">=", start_date), ("date_order", "<=", end_date)]
        if customer_id:
            domain.append(("partner_id", "=", customer_id))
        orders = self.read_group(domain, ["amount_total"], [])
        return {"amount_total": (orders[0]["amount_total"] or 0) if orders else 0}
```

## Tool kinds

| Kind | Invocation |
| --- | --- |
| `generic` | `model.function(**args)` — no record context |
| `generic_model` | `model.function(record=record, **args)` |
| `record` | `record.function(**args)` — the record must match `model_id` |

Rules:

- A tool must always return a `dict`; its keys are declared in `output_schema`.
- All method parameters must be declared in `input_schema`, except `record`.
- `record` is a protected argument, required for `generic_model` and `record`
  tools — it is how integrations pass the record the action applies to.
