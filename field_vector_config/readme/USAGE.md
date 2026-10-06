After the configuration, we can easily compute and search using this vector. For example:

```python
from odoo.addons.ai_tool.tools import aitool


class ProductProduct(models.Model):

    _inherit = "product.product"

    product_vector = ComputedVector(
        compute="_compute_product_vector",
        store=True,
    )

    @api.depends("name", "description")
    def _compute_product_vector(self):
        for record in self:
            record.product_vector = record._encode_vector("product_vector", f"{record.name}\n{record.description}\n{record.description_purchase}")[0]

    def _find_vector_product(self, value, limit=5):
        records = self.search_vector("product_vector", value, limit=limit)
        return [{"id": r.id, "name": r.name, "description": r.description} for r in records]
```