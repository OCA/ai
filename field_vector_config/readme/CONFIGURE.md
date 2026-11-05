With this module, we can easily add a configuration on a vector to configure it dynamically on our database.

```python
from odoo.addons.field_vector_config.fields import ComputedVector


class ResPartner(models.Model):
    _inherit = "res.partner"

    embedding = ComputedVector(string="Embedding")
```

With that, we can go to **Settings / Technical / Database Structure** to add the field manually and configure it.
There you can configure the size of the vector (depends on the method and model), computation information and so on.

Important notes:

- If you make a field that is computed, we recommend to create it in a pre_init_hook to avoid the creation and allow the user to configure it properly
- If you change the size of the vector, update the column. It will update the size and do nothing if it has the proper size.
