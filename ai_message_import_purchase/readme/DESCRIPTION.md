This module adds the document type *Vendor quote (purchase)* to *AI Message
Import* (`ai_message_import`): the vendor quotes found in the received
conversations become draft requests for quotation (`purchase.order`).

- **Vendor**: the contact that is already a vendor is preferred. When it does
  not exist, it is created if the AI identified it with enough confidence and a
  reliable data (VAT, email, phone or address).
- **Products**: besides the common rules, they are searched by the reference and
  the name in the pricelists of the vendor. A missing product is created when
  its line is complete (description, price, known unit, enough confidence),
  with the price of the document as cost: a service when the AI marks the line
  as such or its unit is of time, otherwise a consumable.
- **Price**: the pricelist of the vendor for the quantity, the unit, the
  currency and the dates; otherwise the cost of the product. The price of the
  document is only compared, and the difference is noted.
- **Units**: the purchase unit of the product and its purchase packagings.
- **Dates and delivery**: the date of the document or of each line, otherwise
  the one Odoo computes with the lead time of the vendor. The warehouse of the
  company is searched by its name or address; addresses and locations are
  never created.
- **Reference**: the number of the quote goes to the *Vendor Reference*.
- **Confirmation**: never automatic. With open incidents, *Confirm Order* warns
  before confirming.
