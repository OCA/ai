This module is technical, however, it adds some specific functions that might be used in glue modules.

For example, if we want to add on sales a functionality to find the sales on a period, we should do:

```xml
<odoo>
    <record model="ai.tool" id="total_sale_order_tool">
        <field name="name">total_sale_order</field>
        <field
            name="description"
        >Calculate the total amount of sale orders within a date range and optionally for a specific customer.</field>
        <field name="model_id" ref="model_sale_order" />
        <field name="function_name">_mcp_total_sale_order</field>
    </record>
</odoo>
```

```python
from odoo.addons.ai_tool import aitool

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
    def _mcp_total_sale_order(self, start_date, end_date, customer_id=None):
        domain = [("date_order", ">=", start_date), ("date_order", "<=", end_date)]
        if customer_id:
            domain.append(("partner_id", "=", customer_id))
        orders = self.read_group(domain, ["amount_total"], [])
        return {
            "amount_total": (orders[0]["amount_total"] or 0) if orders else 0,
        }

```

Be aware that this kind of elements must allways return a dict. All the elements will be defined in output_schema.

Also, for the signature of the functions, all fields must be in the inputs with the exception of record.
This argument is protected and is used to define integrations with automation.
This argument is required in `generic_model` and `record` tools.

On `generic_model`s we are expecting this value because we want to do a specific action with the model.
