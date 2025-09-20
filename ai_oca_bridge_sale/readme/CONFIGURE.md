- **Bridge with `Usage = "AI Thread Create"`**
    Processes new sale orders and order lines in the external system for AI-enhanced actions like sales analysis, customer insights, or automated sales processes.

- **Bridge with `Usage = "AI Thread Write"`**
    Updates sale order and order line information in the external system when they are modified in Odoo.

- **Bridge with `Usage = "AI Thread Unlink"`**
    Removes sale order and order line data from the external system when they are deleted from Odoo.

For creating those bridges, apart from the usage of the bridge, the user must define:
- Payload Type: it depends on the endpoint configuration, normally "Record" would work.
- Result Type: depending on your use case.
- Model: select the "Sale Order" or "Sale Order Line" model
- Field: add at least the fields the endpoint is expecting (e.g., name, partner, product, quantity, state, etc.).
- Filter: add a domain for using the bridge only with the sale orders/order lines intended to trigger automatic actions
