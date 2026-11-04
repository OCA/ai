# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command

from odoo.addons.ai_message_import.tests.common import AiMessageImportCase


class AiMessageSaleCase(AiMessageImportCase):
    """Customer orders, with customers, products and prices."""

    DOCUMENT_TYPE = "sale"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax_21 = cls.env["account.tax"].create(
            {
                "name": "Sales 21%",
                "amount": 21,
                "type_tax_use": "sale",
                "company_id": cls.company.id,
            }
        )
        cls.product_tile = cls._create_product("White tile 20x20", "AZ-2020", 12.0)
        cls.product_cement = cls._create_product("Tile adhesive 25kg", "CEM-25", 8.5)
        cls.product_free = cls._create_product("Sample board", "MUE-01", 0.0)
        cls.packaging_box = cls.env["product.packaging"].create(
            {
                "name": "Caja 10",
                "product_id": cls.product_tile.id,
                "qty": 10,
                "sales": True,
            }
        )
        cls.pricelist = cls.env["product.pricelist"].create(
            {
                "name": "Professional customers",
                "currency_id": cls.currency.id,
                "company_id": cls.company.id,
                "item_ids": [
                    Command.create(
                        {
                            "applied_on": "0_product_variant",
                            "product_id": cls.product_tile.id,
                            "compute_price": "fixed",
                            "fixed_price": 9.0,
                        }
                    )
                ],
            }
        )
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Construcciones Levante SL",
                "vat": "ESB87878781",
                "email": "compras@levante.example",
                "is_company": True,
                "customer_rank": 1,
            }
        )
        cls.customer.with_company(
            cls.company
        ).property_product_pricelist = cls.pricelist
        cls.site = cls.env["res.partner"].create(
            {
                "name": "Obra Ruzafa",
                "type": "delivery",
                "parent_id": cls.customer.id,
                "street": "Calle Sueca 21",
                "city": "Valencia",
            }
        )
        cls.freight = cls.env["product.product"].create(
            {
                "name": "Transport",
                "type": "service",
                "sale_ok": True,
                "taxes_id": [Command.set(cls.tax_21.ids)],
            }
        )
        cls.config.freight_product_id = cls.freight

    @classmethod
    def _create_product(cls, name, code, price):
        return cls.env["product.product"].create(
            {
                "name": name,
                "default_code": code,
                "list_price": price,
                "sale_ok": True,
                "type": "consu",
                "taxes_id": [Command.set(cls.tax_21.ids)],
            }
        )

    def _order(self, lines, **values):
        """A customer order as the AI answers it."""
        values.setdefault(
            "partner",
            {
                "name": "Construcciones Levante S.L.",
                "vat": "B87878781",
                "confidence": 0.95,
            },
        )
        values.setdefault("quote_number", "PED-778")
        return self._quote(lines, **values)
