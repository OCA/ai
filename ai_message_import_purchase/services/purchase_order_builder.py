# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Turn a vendor quote into a draft purchase order, or update one.

The common rules are in ``OrderBuilder``. Here: the vendor of the quote, the
prices and lead times of its price lists, the warehouse of the delivery
address, and the products and services created from a quote.
"""

from odoo import _
from odoo.tools import float_is_zero

from odoo.addons.ai_message_import.services.matching import match_warehouse
from odoo.addons.ai_message_import.services.order_builder import OrderBuilder


class PurchaseOrderBuilder(OrderBuilder):
    order_model = "purchase.order"
    line_model = "purchase.order.line"
    order_link = "purchase_order_id"
    line_link = "purchase_line_id"
    qty_field = "product_qty"
    tax_field = "taxes_id"
    line_date_field = "date_planned"
    order_fields = ("partner_ref", "payment_term_id", "picking_type_id")
    line_fields = (
        "product_id",
        "product_qty",
        "product_uom",
        "product_packaging_id",
        "price_unit",
        "discount",
        "date_planned",
    )
    product_ok_field = "purchase_ok"
    packaging_usage = "purchase"
    rank_field = "supplier_rank"
    supplier_steps = True
    confirmed_states = ("purchase", "done")

    def _role(self):
        return _("vendor")

    def _order_label(self):
        return _("purchase order")

    def _auto_create_partner(self):
        return self.config.auto_create_vendor

    def _partner_min_confidence(self):
        return self.config.vendor_min_confidence

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _header_values(self, partner):
        quote = self.quote
        # Only what the quote states: a correction keeps the rest of the order.
        values = {"partner_ref": quote.quote_number} if quote.quote_number else {}
        term = self._payment_term(partner)
        if term is not None:
            values["payment_term_id"] = term.id
        picking_type = self._picking_type()
        if picking_type:
            values["picking_type_id"] = picking_type.id
        return values

    def _default_payment_term(self, partner):
        return partner.with_company(self.company).property_supplier_payment_term_id

    def _picking_type(self):
        quote = self.quote
        address = quote.delivery_address
        if not address:
            return None
        warehouses = match_warehouse(self.env, self.company, address)
        if len(warehouses) == 1 and warehouses.in_type_id:
            self.note(
                _(
                    "Delivery address '%(address)s' matched to the warehouse "
                    "%(warehouse)s.",
                    address=address,
                    warehouse=warehouses.display_name,
                )
            )
            return warehouses.in_type_id
        self.incident(
            "delivery_address",
            _("Delivery address not found"),
            _(
                "The document asks for a delivery to '%(address)s', which matches "
                "%(count)s warehouses of the company. The usual destination of "
                "Odoo is kept; no address, warehouse nor location was created.",
                address=address,
                count=len(warehouses),
            ),
            values={"address": address},
        )
        self.note(
            _(
                "Delivery address '%(address)s' not found: the usual destination is "
                "kept.",
                address=address,
            )
        )
        return None

    def _order_values(self, partner, header):
        quote = self.quote
        vendor = partner.with_company(self.company)
        fiscal_position = (
            self.env["account.fiscal.position"]
            .with_company(self.company)
            ._get_fiscal_position(partner)
        )
        values = {
            "partner_id": partner.id,
            "company_id": self.company.id,
            "currency_id": self.company.currency_id.id,
            "fiscal_position_id": fiscal_position.id,
            "payment_term_id": vendor.property_supplier_payment_term_id.id,
            "origin": quote.name,
            "ai_message_import_sender_id": quote.sender_id.id,
        }
        # As the form of Odoo: the buyer of the vendor, otherwise the user that
        # creates the order.
        if vendor.buyer_id:
            values["user_id"] = vendor.buyer_id.id
        return values

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def _order_uom(self, product):
        return product.uom_po_id

    def _product_creation_blocker(self, qline, uom):
        if not self.config.auto_create_product:
            return _("the automatic creation of products is disabled")
        if qline.confidence < self.config.product_min_confidence:
            return _(
                "the confidence of the line (%(conf).0f%%) is too low",
                conf=qline.confidence * 100,
            )
        if not qline.description:
            return _("the line has no description")
        if not qline.price_known:
            return _("the document gives no price for it")
        if self.converter.error:
            return self.converter.error
        if qline.uom_text and not uom:
            return _("the unit '%(uom)s' does not exist in Odoo", uom=qline.uom_text)
        if self._quoted_price_excluded(qline) is None:
            return _("its price includes taxes at an unknown rate")
        return None

    def _create_product(self, qline, uom):
        uom = uom or self.env.ref("uom.product_uom_unit")
        price = self.converter.convert(self._quoted_price_excluded(qline))
        # A service for the AI, or anything quoted in hours or days.
        service = qline.is_service or uom.category_id == self.env.ref(
            "uom.uom_categ_wtime"
        )
        vals = {
            "name": qline.description,
            "purchase_ok": True,
            "company_id": self.company.id,
            "uom_id": uom.id,
            "uom_po_id": uom.id,
            "standard_price": price,
        }
        vals.update(self._product_type_values(service))
        if service:
            taxes = self._service_purchase_taxes()
            if taxes:
                vals["supplier_taxes_id"] = [(6, 0, taxes.ids)]
        product = self.env["product.product"].create(vals)
        qline.write({"product_id": product.id, "product_match": "created"})
        self.env["ai.message.import.product.mapping"]._learn(
            qline, product, source="created"
        )
        if service:
            message = _(
                "Service %(product)s created from the document, with the quoted price "
                "%(price)s as cost.",
                product=product.display_name,
                price=self._amount(price),
            )
        else:
            message = _(
                "Product %(product)s created from the document, with the quoted price "
                "%(price)s as cost.",
                product=product.display_name,
                price=self._amount(price),
            )
        self.note(message)
        return product

    def _product_type_values(self, service=False):
        return {"type": "service" if service else "consu"}

    def _service_purchase_taxes(self):
        """Default purchase taxes of the company, in their service version.

        A tax for goods is replaced by the only purchase tax for services of the
        company with the same rate, group and distribution (21% S for 21% B in
        Spain). Without such a single tax, the default one is kept.
        """
        Tax = self.env["account.tax"]

        def shape(tax):
            return sorted(
                (line.repartition_type, line.factor_percent)
                for line in tax.invoice_repartition_line_ids
            )

        taxes = Tax
        for tax in self.company.account_purchase_tax_id:
            if tax.tax_scope != "consu":
                taxes |= tax
                continue
            twins = Tax.search(
                [
                    ("company_id", "=", self.company.id),
                    ("type_tax_use", "=", "purchase"),
                    ("tax_scope", "=", "service"),
                    ("amount_type", "=", tax.amount_type),
                    ("amount", "=", tax.amount),
                    ("tax_group_id", "=", tax.tax_group_id.id),
                    ("price_include", "=", tax.price_include),
                ]
            ).filtered(lambda twin, tax=tax: shape(twin) == shape(tax))
            taxes |= twins if len(twins) == 1 else tax
        return taxes

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    def _line_date(self, qline):
        return self._quoted_line_date(qline)

    def _recompute_line_prices(self, line):
        line._compute_price_unit_and_date_planned_and_name()

    def _change_line_product(self, line, product_id):
        # Its description, its taxes and no price of the former product.
        line.write({"product_id": product_id, "price_unit": 0.0})
        line._product_id_change()

    def _seller(self, line):
        return line.product_id._select_seller(
            partner_id=line.order_id.partner_id,
            quantity=line.product_qty,
            date=line.order_id.date_order.date(),
            uom_id=line.product_uom,
            params=line._get_select_sellers_params(),
        )

    def _odoo_discount(self, line):
        seller = self._seller(line)
        return seller.discount if seller else 0.0

    def _price_origin(self, line):
        if self._seller(line):
            return _("vendor price list")
        return _("product cost")

    def _check_zero_price(self, line, plan):
        if self._seller(line) or not float_is_zero(
            line.price_unit, precision_rounding=line.currency_id.rounding
        ):
            return
        self.incident(
            "price_zero",
            _("Zero cost for %(line)s", line=plan.label),
            _(
                "%(product)s has no vendor price and its cost is zero: the price 0 "
                "is kept, check it before confirming. Quoted price: %(quoted)s.",
                product=line.product_id.display_name,
                quoted=self._amount(plan.quoted_price)
                if plan.quoted_price is not None
                else "-",
            ),
            qline=plan.qline,
        )

    def _computed_date_note(self, line, plan):
        seller = self._seller(line)
        self.note(
            _(
                "%(line)s: no delivery date in the document, Odoo planned it on "
                "%(date)s (%(delay)s days of vendor lead time).",
                line=plan.label,
                date=self._date(line.date_planned),
                delay=seller.delay if seller else 0,
            )
        )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _freight_line_values(self, order, product, price):
        return {
            "order_id": order.id,
            "product_id": product.id,
            "product_qty": 1.0,
            "product_uom": product.uom_po_id.id,
            "price_unit": price,
            "ai_message_import_line_kind": "freight",
            "sequence": 9999,
        }

    def _freight_tax_rate(self, product, order):
        taxes = order.fiscal_position_id.map_tax(
            product.supplier_taxes_id._filter_taxes_by_company(self.company)
        )
        if not taxes:
            return 0.0
        result = taxes.compute_all(100.0, currency=order.currency_id, product=product)
        excluded = result["total_excluded"]
        return (
            (result["total_included"] - excluded) / excluded * 100 if excluded else 0.0
        )
