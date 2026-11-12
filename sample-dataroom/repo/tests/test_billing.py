from decimal import Decimal

import pytest

from ledgerlight.billing import finalize, invoice_total
from ledgerlight.models import Invoice, LineItem


def make_invoice(discount: str = "0") -> Invoice:
    return Invoice(
        customer_id="cus_test",
        currency="USD",
        items=[LineItem("Seat licence", 3, Decimal("40.00"))],
        discount_pct=Decimal(discount),
    )


def test_total_applies_tax():
    assert invoice_total(make_invoice(), tax_rate=0.1) == Decimal("132.00")


def test_total_applies_discount_before_tax():
    assert invoice_total(make_invoice("50"), tax_rate=0.1) == Decimal("66.00")


def test_cannot_finalize_empty_invoice():
    with pytest.raises(ValueError):
        finalize(Invoice(customer_id="cus_test", currency="USD"))
