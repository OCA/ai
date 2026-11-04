# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from ..services.tools import (
    AUTOMATION_CONTEXT_KEY,
    NO_AUTO_APPLY_KEY,
    automation_user,
    normalize_code,
)

# What a person fixes on a document or on its lines when an incident keeps it,
# or a line, out of its order: the document is then applied again by itself.
FIX_FIELDS = {"partner_id", "document_type"}
LINE_FIX_FIELDS = {"product_id", "uom_id", "quantity", "description", "product_code"}

# Incidents produced by the application of a quote, replaced on each one.
APPLY_INCIDENT_TYPES = (
    "partner",
    "product",
    "uom",
    "invalid_line",
    "price_zero",
    "tax_missing",
    "tax_difference",
    "currency",
    "discount",
    "freight",
    "delivery_date",
    "payment_term",
    "delivery_address",
    "pack_size",
    "total_difference",
    "duplicate",
    "update_ambiguous",
    "order_locked",
    "no_document",
    "human_conflict",
    "processing_error",
)


class AiMessageImportDocument(models.Model):
    """A document interpreted by the AI from a conversation.

    A vendor quote, a customer order...: the AI gives each document its type
    among the installed ones, and the module of that type turns it into an order
    of Odoo.
    """

    _name = "ai.message.import.document"
    _description = "Interpreted Document"
    _inherit = ["mail.thread"]
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True, copy=False, default="/")
    conversation_id = fields.Many2one(
        "mail.message.import.conversation",
        string="Conversation",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    channel_id = fields.Many2one(
        related="conversation_id.channel_id", store=True, string="Receiving channel"
    )
    # Where it came from, to divide the documents by channel and address
    authorized_address_id = fields.Many2one(
        related="conversation_id.authorized_address_id",
        store=True,
        string="Sent from",
        index="btree_not_null",
    )
    sender_address = fields.Char(
        related="conversation_id.sender_address", store=True, string="Address"
    )
    origin_display = fields.Char(related="conversation_id.origin_display")
    sender_id = fields.Many2one(
        "mail.message.import.sender",
        string="Sender",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    document_type = fields.Selection(
        selection="_selection_document_type",
        index=True,
        tracking=True,
        help="Decided by the AI for each document: it tells the order created "
        "from it. When it is wrong, change it and apply the document again.",
    )
    processing_ref = fields.Char(string="Processing", readonly=True)
    state = fields.Selection(
        [
            ("draft", "Interpreted"),
            ("pending", "Pending review"),
            ("duplicate", "Possible duplicate"),
            ("done", "Order created"),
            ("cancelled", "Discarded"),
        ],
        default="draft",
        required=True,
        readonly=True,
        tracking=True,
        index=True,
    )
    message_ids = fields.Many2many(
        "mail.message.import.message",
        "ai_message_import_document_message_rel",
        "document_id",
        "message_id",
        string="Messages",
        readonly=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ai_message_import_document_attachment_rel",
        "document_id",
        "attachment_id",
        string="Documents",
        readonly=True,
    )
    line_ids = fields.One2many(
        "ai.message.import.document.line", "document_id", copy=False
    )
    extraction = fields.Json(
        readonly=True,
        help="Values of the document as interpreted by the AI and validated.",
    )
    extraction_display = fields.Text(
        string="Interpreted values", compute="_compute_extraction_display"
    )
    # Partner: the vendor or the customer, depending on the document type
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor / Customer",
        check_company=True,
        tracking=True,
        help="Partner of the order: the vendor of a document, the customer of an "
        "order. Select it when it was not identified.",
    )
    partner_match_method = fields.Selection(
        [
            ("vat", "VAT number"),
            ("email", "email"),
            ("mapping", "learned equivalence"),
            ("ref", "internal reference"),
            ("name", "name"),
            ("name_part", "part of the name"),
            ("created", "creation"),
            ("manual", "manual selection"),
        ],
        readonly=True,
    )
    partner_name = fields.Char(readonly=True)
    partner_vat = fields.Char(string="VAT", readonly=True)
    partner_confidence = fields.Float(readonly=True, digits=(3, 2))
    # Header values, editable before applying the quote again
    quote_number = fields.Char(string="Document number", tracking=True)
    quote_number_key = fields.Char(
        string="Document number key",
        compute="_compute_quote_number_key",
        store=True,
        index=True,
    )
    quote_date = fields.Date(string="Document date", tracking=True)
    currency_code = fields.Char(string="Currency", readonly=True)
    prices_include_tax = fields.Boolean(readonly=True)
    delivery_date = fields.Date(tracking=True)
    delivery_address = fields.Char(tracking=True)
    payment_terms_text = fields.Char(string="Quoted payment terms", readonly=True)
    payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Payment terms to apply",
        check_company=True,
        help="Forces the payment terms of the order, instead of searching the "
        "quoted ones.",
    )
    amount_untaxed_doc = fields.Float(string="Quoted untaxed", readonly=True)
    amount_tax_doc = fields.Float(string="Quoted taxes", readonly=True)
    amount_total_doc = fields.Float(string="Quoted total", readonly=True)
    shipping_amount_doc = fields.Float(string="Quoted transport", readonly=True)
    global_discount_doc = fields.Char(string="Quoted global discount", readonly=True)
    clarifications = fields.Text(readonly=True)
    ai_warnings = fields.Text(string="Interpretation warnings", readonly=True)
    confidence = fields.Float(readonly=True, digits=(3, 2))
    # Relation with the previous quotes
    relation = fields.Selection(
        [("new", "New"), ("update", "Correction"), ("duplicate", "Duplicate")],
        default="new",
        readonly=True,
    )
    relation_reason = fields.Text(string="Reason given", readonly=True)
    target_reference = fields.Char(readonly=True)
    target_quote_id = fields.Many2one(
        "ai.message.import.document",
        string="Corrected document",
        readonly=True,
        ondelete="set null",
    )
    remove_missing_lines = fields.Boolean(readonly=True)
    duplicate_of_id = fields.Many2one(
        "ai.message.import.document", string="Duplicate of", readonly=True
    )
    duplicate_ids = fields.One2many(
        "ai.message.import.document", "duplicate_of_id", string="Received again in"
    )
    duplicate_evidence = fields.Text(readonly=True)
    skip_duplicate_check = fields.Boolean(readonly=True, copy=False)
    # Result
    processing_notes = fields.Html(readonly=True, sanitize=True)
    incident_ids = fields.One2many(
        "mail.message.import.incident", "document_id", string="Incidents"
    )
    open_incident_count = fields.Integer(compute="_compute_open_incident_count")
    open_incident_summary = fields.Text(compute="_compute_open_incident_count")
    change_ids = fields.One2many(
        "ai.message.import.change", "document_id", string="History"
    )
    attachment_count = fields.Integer(
        string="Number of files", compute="_compute_related_counts"
    )
    message_count = fields.Integer(
        string="Number of messages", compute="_compute_related_counts"
    )
    change_count = fields.Integer(
        string="Number of changes", compute="_compute_related_counts"
    )
    duplicate_count = fields.Integer(
        string="Number of duplicates", compute="_compute_related_counts"
    )
    # New for each person until they open it, like an unread email
    seen_user_ids = fields.Many2many(
        "res.users",
        "ai_message_import_document_seen_rel",
        "document_id",
        "user_id",
        string="Seen by",
        readonly=True,
        copy=False,
    )
    is_new = fields.Boolean(
        string="New",
        compute="_compute_is_new",
        search="_search_is_new",
        help="You have not opened the document yet.",
    )

    @api.model
    def _selection_document_type(self):
        return [(key, rules["label"]) for key, rules in self._document_types().items()]

    @api.depends("quote_number")
    def _compute_quote_number_key(self):
        for quote in self:
            quote.quote_number_key = normalize_code(quote.quote_number) or False

    @api.depends("extraction")
    def _compute_extraction_display(self):
        for quote in self:
            quote.extraction_display = json.dumps(
                quote.extraction or {}, indent=2, ensure_ascii=False
            )

    @api.depends("incident_ids.state", "incident_ids.name")
    def _compute_open_incident_count(self):
        for quote in self:
            incidents = quote.incident_ids.filtered(lambda i: i.state == "open")
            quote.open_incident_count = len(incidents)
            quote.open_incident_summary = (
                "\n".join(f"- {incident.name}" for incident in incidents) or False
            )

    @api.depends("seen_user_ids")
    @api.depends_context("uid")
    def _compute_is_new(self):
        for quote in self:
            quote.is_new = self.env.user not in quote.seen_user_ids

    def _search_is_new(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise UserError(_("Operation not supported."))
        new = (operator == "=") == value
        return [("seen_user_ids", "not in" if new else "in", [self.env.uid])]

    def action_mark_seen(self):
        """The user saw the documents: they are no longer new for them."""
        self.filtered("is_new").write({"seen_user_ids": [Command.link(self.env.uid)]})
        return True

    @api.depends("attachment_ids", "message_ids", "change_ids", "duplicate_ids")
    def _compute_related_counts(self):
        for quote in self:
            quote.attachment_count = len(quote.attachment_ids)
            quote.message_count = len(quote.message_ids)
            quote.change_count = len(quote.change_ids)
            quote.duplicate_count = len(quote.duplicate_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = (
                    self.env["ir.sequence"]
                    .sudo()
                    .next_by_code("ai.message.import.document")
                    or "/"
                )
        return super().create(vals_list)

    def write(self, vals):
        if "partner_id" in vals and not self.env.context.get(AUTOMATION_CONTEXT_KEY):
            vals["partner_match_method"] = "manual" if vals["partner_id"] else False
        if "document_type" in vals:
            self._check_type_change(vals["document_type"])
        # Its lines are applied with the document, after the whole write.
        res = super(
            AiMessageImportDocument, self.with_context(**{NO_AUTO_APPLY_KEY: True})
        ).write(vals)
        if vals.get("partner_id") and not self.env.context.get(AUTOMATION_CONTEXT_KEY):
            # Chosen by a person: learn the name it was written with.
            for quote in self.filtered("partner_name"):
                self.env["ai.message.import.partner.mapping"]._learn(
                    quote, quote.partner_id
                )
        if self._fixes_something(vals):
            self._apply_after_fix()
        return res

    def _fixes_something(self, vals):
        """Whether a person changed what an incident asks to fix."""
        if self.env.context.get(AUTOMATION_CONTEXT_KEY) or self.env.context.get(
            NO_AUTO_APPLY_KEY
        ):
            return False
        lines = [
            command[2]
            for command in vals.get("line_ids") or []
            if command[0] == Command.UPDATE
        ]
        return any(vals.get(name) for name in FIX_FIELDS) or any(
            LINE_FIX_FIELDS & set(values) for values in lines
        )

    def _apply_after_fix(self):
        """Apply again the documents a person fixed, when an incident kept them
        or some of their lines out of their orders: the order is then created,
        or completed, without pressing "Apply again"."""
        quotes = self.filtered(
            lambda q: (
                q.state in ("draft", "pending")
                or (q.state == "done" and "pending" in q.line_ids.mapped("state"))
            )
        )
        if not quotes:
            return
        try:
            quotes._check_order_rights()
        except UserError:
            # Whoever cannot create the orders only fixes the document.
            return
        for quote in quotes:
            quote._apply_quote(quote._manual_ref())

    def _check_type_change(self, document_type):
        """A document keeps its type while it has an order that is not cancelled."""
        for quote in self.filtered(lambda q: q.document_type != document_type):
            order = quote.document_type and quote._get_order()
            if order and order.state != "cancel":
                raise UserError(
                    _(
                        "%(quote)s already has the order %(order)s: cancel it "
                        "before changing the document type.",
                        quote=quote.name,
                        order=order.display_name,
                    )
                )

    def clarification_list(self):
        self.ensure_one()
        return [line for line in (self.clarifications or "").splitlines() if line]

    # ------------------------------------------------------------------
    # Creation from the answer of the AI
    # ------------------------------------------------------------------

    @api.model
    def _create_from_result(
        self, conversation, result, message_labels, document_labels, previous
    ):
        quotes = self.browse()
        all_attachments = conversation.message_ids.attachment_ids
        single = len(result["quotes"]) == 1
        for data in result["quotes"]:
            messages = (
                self.env["mail.message.import.message"].browse(
                    [message_labels[ref].id for ref in data["message_refs"]]
                )
                or conversation.message_ids
            )
            attachments = self.env["ir.attachment"].browse(
                [document_labels[ref].id for ref in data["document_refs"]]
            )
            if not attachments and single:
                attachments = all_attachments
            target = previous.get(data["target_reference"]) or self.browse()
            totals = data["totals"]
            discount = data["global_discount"]
            partner = data["partner"]
            delivery = data["delivery"]
            quotes |= self.create(
                {
                    "conversation_id": conversation.id,
                    "sender_id": conversation.sender_id.id,
                    "company_id": conversation.company_id.id,
                    "document_type": data["document_type"],
                    "processing_ref": conversation.processing_ref,
                    "message_ids": [(6, 0, messages.ids)],
                    "attachment_ids": [(6, 0, attachments.ids)],
                    "extraction": data,
                    "partner_name": partner["name"],
                    "partner_vat": partner["vat"],
                    "partner_confidence": partner["confidence"],
                    "quote_number": data["quote_number"] or False,
                    "quote_date": data["quote_date"] or False,
                    "currency_code": data["currency"] or False,
                    "prices_include_tax": data["prices_include_tax"],
                    "delivery_date": delivery["date"] or False,
                    "delivery_address": delivery["address"] or False,
                    "payment_terms_text": data["payment_terms"]["text"]
                    or (
                        _("%(days)s days", days=data["payment_terms"]["days"])
                        if data["payment_terms"]["days"] is not None
                        else False
                    ),
                    "amount_untaxed_doc": totals["untaxed"] or 0.0,
                    "amount_tax_doc": totals["tax"] or 0.0,
                    "amount_total_doc": totals["total"] or 0.0,
                    "shipping_amount_doc": data["shipping"]["amount"] or 0.0,
                    "global_discount_doc": self._discount_text(discount),
                    "clarifications": "\n".join(data["clarifications"]) or False,
                    "ai_warnings": "\n".join(data["warnings"]) or False,
                    "confidence": data["confidence"],
                    "relation": data["relation"],
                    "relation_reason": data["relation_reason"] or False,
                    "target_reference": data["target_reference"] or False,
                    "target_quote_id": target.id,
                    "remove_missing_lines": data["remove_missing_lines"],
                    "line_ids": [
                        (
                            0,
                            0,
                            self.env["ai.message.import.document.line"]._values_from(
                                line
                            ),
                        )
                        for line in data["lines"]
                    ],
                }
            )
        return quotes

    @api.model
    def _discount_text(self, discount):
        parts = []
        if discount.get("percent"):
            parts.append(f"{discount['percent']:g}%")
        if discount.get("amount"):
            parts.append(f"{discount['amount']:.2f}")
        return " / ".join(parts) or False

    # ------------------------------------------------------------------
    # Application to the orders, by document type
    # ------------------------------------------------------------------

    def _automation_env_self(self):
        self.ensure_one()
        lang = self.company_id.partner_id.lang or self.env.lang or "en_US"
        return (
            self.with_user(automation_user(self.env, self.company_id))
            .sudo()
            .with_company(self.company_id)
            .with_context(lang=lang, **{AUTOMATION_CONTEXT_KEY: True})
        )

    @api.model
    def _document_types(self):
        """The document types of the installed modules, for the AI to choose.

        Each module of a type adds its own:
        ``{key: {"label": str, "builder": OrderBuilder subclass}}``. When a
        document is of the type, and who its partner is, the AI reads it in the
        prompt ``document_type.<key>`` (``ai.message.import.prompt``).
        """
        return {}

    @api.model
    def _document_rules(self, document_type):
        rules = self._document_types().get(document_type)
        if not rules:
            raise UserError(
                _(
                    "No installed module processes the documents of type "
                    "'%(type)s'. Choose another document type.",
                    type=document_type or "-",
                )
            )
        return rules

    def _builder(self):
        self.ensure_one()
        return self._document_rules(self.document_type)["builder"](self)

    def _get_order(self):
        """The order of the document."""
        self.ensure_one()
        link = self._document_rules(self.document_type)["builder"].order_link
        return self[link]

    def _superseded_note(self):
        """Note of the incidents that a new application supersedes, in the
        language of the environment of the document."""
        return _("Superseded by a new application.")

    def _apply_quote(self, processing_ref=None):
        """Create or update the order of the quote.

        Runs in the controlled technical context of the module: draft orders
        only, never confirmed nor cancelled.
        """
        self.ensure_one()
        quote = self._automation_env_self()
        quote.sender_id._lock_for_quotes()
        if processing_ref:
            quote.processing_ref = processing_ref
        quote.incident_ids.filtered(
            lambda i: i.state == "open" and i.incident_type in APPLY_INCIDENT_TYPES
        ).write(
            {
                "state": "resolved",
                "resolution_note": quote._superseded_note(),
                "resolved_date": fields.Datetime.now(),
            }
        )
        quote.line_ids.filtered(lambda line: line.state != "removed").write(
            {"state": "draft"}
        )
        return quote._builder().run()

    def _check_order_rights(self):
        for document_type in set(self.mapped("document_type")):
            model = self._document_rules(document_type)["builder"].order_model
            if not self.env[model].check_access_rights("create", False):
                raise UserError(
                    _(
                        "You need the rights to create or update %(orders)s.",
                        orders=self.env["ir.model"]._get(model).name,
                    )
                )

    def _manual_ref(self):
        return _(
            "%(conversation)s / manual by %(user)s on %(date)s",
            conversation=self.conversation_id.name,
            user=self.env.user.name,
            date=fields.Datetime.now(),
        )

    def action_apply(self):
        """Apply the document again, after correcting it."""
        self._check_order_rights()
        for quote in self:
            if quote.state == "cancelled":
                raise UserError(_("A discarded document cannot be applied."))
            quote._apply_quote(quote._manual_ref())

    def action_not_duplicate(self):
        self._check_order_rights()
        for quote in self.filtered(lambda q: q.state == "duplicate"):
            quote.sudo().write({"skip_duplicate_check": True, "relation": "new"})
            quote._apply_quote(quote._manual_ref())

    def action_apply_as_correction(self):
        """Apply a duplicate as a correction of the document it duplicates."""
        self._check_order_rights()
        for quote in self.filtered(lambda q: q.state == "duplicate"):
            original = quote.duplicate_of_id or quote.target_quote_id
            if not original._get_order():
                raise UserError(
                    _("%(ref)s has no order to correct.", ref=original.name)
                )
            quote.sudo().write({"relation": "update", "target_quote_id": original.id})
            quote._apply_quote(quote._manual_ref())

    def action_discard(self):
        self.write({"state": "cancelled"})
        self.incident_ids.filtered(lambda i: i.state == "open").write(
            {
                "state": "dismissed",
                "resolution_note": _("The document was discarded."),
                "resolved_by_id": self.env.uid,
                "resolved_date": fields.Datetime.now(),
            }
        )

    def action_view_order(self):
        self.ensure_one()
        order = self._get_order()
        return {
            "type": "ir.actions.act_window",
            "res_model": order._name,
            "res_id": order.id,
            "view_mode": "form",
        }

    # ------------------------------------------------------------------
    # Buttons of the form: what came with the document and what it caused
    # ------------------------------------------------------------------

    def _action_records(self, xmlid, records):
        """The action ``xmlid`` on ``records``, straight on its form when there
        is a single one."""
        action = self.env["ir.actions.act_window"]._for_xml_id(xmlid)
        action["context"] = {}
        if len(records) == 1:
            action.update(
                {"res_id": records.id, "view_mode": "form", "views": [(False, "form")]}
            )
        else:
            action["domain"] = [("id", "in", records.ids)]
        return action

    def action_view_incidents(self):
        """The open incidents, or all of them when none is open."""
        self.ensure_one()
        incidents = self.incident_ids.filtered(lambda i: i.state == "open")
        return self._action_records(
            "mail_message_import.action_mail_message_import_incident",
            incidents or self.incident_ids,
        )

    def action_view_attachments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Files"),
            "res_model": "ir.attachment",
            "view_mode": "kanban,tree,form",
            "domain": [("id", "in", self.attachment_ids.ids)],
            "context": {"create": False},
        }

    def action_view_messages(self):
        self.ensure_one()
        return self._action_records(
            "mail_message_import.action_mail_message_import_message", self.message_ids
        )

    def action_view_batch(self):
        self.ensure_one()
        return self._action_records(
            "mail_message_import.action_mail_message_import_conversation",
            self.conversation_id,
        )

    def action_view_changes(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "ai_message_import.action_ai_message_import_change"
        )
        action["domain"] = [("document_id", "=", self.id)]
        action["context"] = {}
        return action

    def action_view_duplicates(self):
        self.ensure_one()
        return self._action_records(
            "ai_message_import.action_ai_message_import_document", self.duplicate_ids
        )


class AiMessageImportDocumentLine(models.Model):
    _name = "ai.message.import.document.line"
    _description = "Interpreted Document Line"
    _order = "document_id, sequence, id"

    document_id = fields.Many2one(
        "ai.message.import.document", required=True, ondelete="cascade", index=True
    )
    sender_id = fields.Many2one(related="document_id.sender_id", store=True)
    company_id = fields.Many2one(related="document_id.company_id", store=True)
    sequence = fields.Integer(default=10)
    product_code = fields.Char(string="Reference")
    own_code = fields.Char(
        string="Our reference",
        help="Reference of the company stated by the document, if any.",
    )
    barcode = fields.Char()
    description = fields.Char()
    quantity = fields.Float(digits="Product Unit of Measure")
    uom_text = fields.Char(string="Quoted unit")
    uom_id = fields.Many2one(
        "uom.uom", string="Unit to apply", help="Forces the unit of the quantity."
    )
    price_unit = fields.Float(string="Quoted price", digits="Product Price")
    price_known = fields.Boolean(string="Price quoted")
    discount_percent = fields.Float(string="Quoted discount (%)", digits="Discount")
    subtotal = fields.Float(string="Quoted subtotal")
    tax_percent = fields.Float(string="Quoted tax (%)")
    tax_known = fields.Boolean(string="Tax quoted")
    delivery_date = fields.Date()
    is_service = fields.Boolean(
        string="Service",
        help="The line is a service (work, hours, subscription...). A product "
        "created from it is a service.",
    )
    confidence = fields.Float(digits=(3, 2))
    product_id = fields.Many2one(
        "product.product",
        help="Product of Odoo. Correcting it teaches the module the equivalence for "
        "this sender and partner.",
    )
    product_match = fields.Selection(
        [
            ("mapping", "learned equivalence"),
            ("supplier_code", "vendor reference"),
            ("internal_reference", "internal reference"),
            ("barcode", "barcode"),
            ("supplier_name", "vendor product name"),
            ("name", "product name"),
            ("ai", "choice of the AI"),
            ("created", "created"),
            ("manual", "manual"),
        ],
        string="Identified by",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "To apply"),
            ("applied", "On the order"),
            ("pending", "Pending"),
            ("removed", "Removed by a person"),
        ],
        default="draft",
        readonly=True,
    )
    validation_errors = fields.Text(readonly=True)
    ai_warnings = fields.Text(string="Warnings", readonly=True)
    original_values = fields.Json(readonly=True)

    @api.model
    def _values_from(self, line):
        return {
            "sequence": line["sequence"],
            "product_code": line["product_code"] or False,
            "own_code": line.get("own_code") or False,
            "barcode": line.get("barcode") or False,
            "description": line["description"] or False,
            "quantity": line["quantity"] or 0.0,
            "uom_text": line["uom"] or False,
            "price_unit": line["price_unit"] or 0.0,
            "price_known": line["price_unit"] is not None,
            "discount_percent": line["discount_percent"] or 0.0,
            "subtotal": line["subtotal"] or 0.0,
            "tax_percent": line["tax_percent"] or 0.0,
            "tax_known": line["tax_percent"] is not None,
            "delivery_date": line["delivery_date"] or False,
            "is_service": line.get("is_service", False),
            "confidence": line["confidence"],
            "validation_errors": "\n".join(line["errors"]) or False,
            "ai_warnings": "\n".join(line["warnings"]) or False,
            "original_values": line,
        }

    def write(self, vals):
        if not self.env.context.get(AUTOMATION_CONTEXT_KEY):
            if "price_unit" in vals and "price_known" not in vals:
                vals["price_known"] = True
            if "tax_percent" in vals and "tax_known" not in vals:
                vals["tax_known"] = True
            if {"quantity", "description", "product_code"} & set(vals):
                # A person corrected the interpretation.
                vals.setdefault("validation_errors", False)
            if vals.get("product_id"):
                vals["product_match"] = "manual"
        res = super().write(vals)
        if vals.get("product_id") and not self.env.context.get(AUTOMATION_CONTEXT_KEY):
            for line in self:
                self.env["ai.message.import.product.mapping"].sudo()._learn(
                    line, line.product_id, source="manual"
                )
        fixed = LINE_FIX_FIELDS & set(vals) and not (
            self.env.context.get(AUTOMATION_CONTEXT_KEY)
            or self.env.context.get(NO_AUTO_APPLY_KEY)
        )
        if vals.get("uom_id") and not self.env.context.get(AUTOMATION_CONTEXT_KEY):
            for line in self:
                self.env["ai.message.import.uom.mapping"].sudo()._learn(
                    line, line.uom_id
                )
        if fixed:
            self.document_id._apply_after_fix()
        return res
