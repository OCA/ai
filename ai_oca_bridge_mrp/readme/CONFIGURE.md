- **Bridge with `Usage = "AI Thread Create"`**
    Processes new MRP workorder in the external system for AI-enhanced actions like lead enrichment or tailored follow up emails.

- **Bridge with `Usage = "AI Thread Write"`**
    Updates lead information in the external system when leads are modified in Odoo.

- **Bridge with `Usage = "AI Thread Unlink"`**
    Removes lead data from the external system when leads are deleted from Odoo.

For creating those bridges, apart from the usage of the bridge, the user must define:
- Payload Type: it depends on the endpoint configuration, normally "Record" would work.
- Result Type: depending on your use case.
- Model: select the "MRP workorder" model
- Field: add at least the fields the endpoint is expecting (e.g., name, email, phone, company, etc.).
- Filter: add a domain for using the bridge only with the leads intended to trigger automatic actions
