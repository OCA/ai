This module allows adding extra parameters to be sent in the bridge's payloads, using Python expressions.
These parameters, unlike fields, can be used independently from the model.

Extra Parameters
================

Create extra parameters by navigating to: **AI Bridge → AI Bridge Extra Parameters**.  
Extra parameters define what additional information will be available in the payload.

Fields Description
------------------

**Parameter Type:**

- **Record**:  
  Evaluated in the context of the record being processed.

- **Bridge Self**:  
  Evaluated in the context of the AI Bridge itself (useful for using ``self.env[...]``).

**Name:**  
Name for this extra parameter.

**Value:**  
The actual information the agent will use.

- Use curly braces ``{}`` for dynamic values.  
  Example: ``{object.name}`` for ``object.name``,  
  ``{object.env["product.product"].search([]).mapped("name")}`` for passing all product names.

- Without braces: the agent receives literal text.
