This module adds the document type *Customer order (sale)* to *AI Message
Import* (`ai_message_import`): the customer orders found in the received
conversations become draft sales quotations (`sale.order`).

- **Customer**: the contact that is already a customer is preferred. When it
  does not exist, it is created only with reliable data: a name, enough
  confidence and a VAT, email, phone or address. Otherwise an incident keeps
  the quotation until a person chooses the customer.
- **Products**: never created. A product that is not identified leaves its line
  pending with an incident; the other lines make the quotation.
- **Price**: the pricelist of the customer, or the sales price of the product,
  with the standard computation of Odoo. The price of the document is only
  compared. A pricelist in another currency is not used, with an incident.
- **Units**: the unit of the product and its sales packagings.
- **Delivery**: the date of the order goes to the *Delivery Date*. The address
  is searched among the delivery addresses of the customer; addresses are
  never created.
- **Reference and payment terms**: the number of the order goes to the
  *Customer Reference*; the payment terms of the customer are kept unless the
  order gives other equivalent ones.
- **Confirmation**: never automatic. With open incidents, *Confirm* warns
  before confirming.
