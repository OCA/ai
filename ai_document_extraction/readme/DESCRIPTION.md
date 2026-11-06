This module extracts structured invoice data (partner, invoice number, payment
reference, date, currency, lines and amounts) from uploaded PDF or image
documents by rendering all document pages and sending them through a configured
`ai.connection`.

The extracted data is applied to draft customer invoices and vendor bills
(`account.move`) either automatically when importing/uploading an attachment on
a journal with an AI connection configured, or on demand via the **Extract with
AI** button. If the partner name cannot be matched automatically, a review
wizard lets the user select or create the partner.
