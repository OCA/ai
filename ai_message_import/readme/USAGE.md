- *Message Import > Panel* shows, for each receiving channel, the documents to
  review, the new ones and the incidents.
- *Message Import > To review > Documents to review* lists the documents that
  are pending, possible duplicates or with open incidents; *New documents*,
  the ones you have not opened yet.
- *Message Import > To review > Incidents* tells what happened and how to solve
  it. For a partner, a product or a unit, choose the record and press **Apply
  and learn**: the document is applied again, and the open incidents written
  the same way are solved with it. Once the cause of any other incident is
  corrected, press **Retry**.
- An order with open incidents warns about them, and asks for a confirmation
  before it is confirmed.
- *Message Import > Configuration > What the AI learned* lists the products,
  contacts and units learned, which can also be added by hand.

For developers, a module of a document type:

- adds its type to `ai.message.import.document._document_types()`, with its
  label and the builder of its orders, a subclass of
  `services.order_builder.OrderBuilder`;
- creates the prompt that describes it, with the code
  `document_type.<type>`;
- adds `ai.message.import.order.mixin` to its orders and
  `ai.message.import.order.line.mixin` to their lines.

A module that keeps a balance of AI tokens overrides
`mail.message.import.conversation._add_ai_tokens()`.
