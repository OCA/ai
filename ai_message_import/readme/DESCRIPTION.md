This module reads with an AI the conversations received by *Mail Message
Import* (`mail_message_import`) and turns the commercial documents they bring
(vendor quotes, customer orders...) into draft orders.

The AI only interprets: Odoo validates every answer and decides. Nothing
coming from the AI is used before it is validated, the prices of Odoo prevail,
and when in doubt an incident is created instead of guessing.

- The **AI connection** of the company (`ai_connection`, OCA/ai) reads the
  whole conversation: the texts, the PDF and the images, and the Word, Excel,
  CSV and forwarded emails turned into text. It tells the documents of the
  installed types and the corrections of the previous ones.
- Each **interpreted document** keeps what the AI read: the partner, the
  number, the date, the lines, the payment terms, the totals... The module of
  its type (purchases, sales...) creates or updates its draft order.
- The partner, the products and the units are found by exact rules (VAT,
  references, barcodes, names, learned equivalences). The lines no rule
  identifies can be chosen by the AI among the most similar products.
- What cannot be decided safely becomes an **incident**: an unknown partner or
  product, a price or total difference, a possible duplicate... The incidents
  of a partner, a product or a unit are solved by choosing the record and
  pressing **Apply and learn**: the choice is learned for the next documents
  written the same way.
- The **history of changes** keeps every value an update of the AI changed on
  an order, and a value changed by a person is never overwritten.

This module knows no document type: install at least one, as
`ai_message_import_purchase` or `ai_message_import_sale`, and a channel of
`mail_message_import`, as `mail_message_import_email` or
`mail_message_import_whatsapp`.
