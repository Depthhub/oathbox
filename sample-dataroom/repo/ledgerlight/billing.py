from decimal import Decimal, ROUND_HALF_UP

from .config import DEFAULT_TAX_RATE, MAX_LINE_ITEMS
from .models import Invoice

CENT = Decimal("0.01")


def invoice_total(invoice: Invoice, tax_rate: float = DEFAULT_TAX_RATE) -> Decimal:
    if len(invoice.items) > MAX_LINE_ITEMS:
        raise ValueError("too many line items")
    subtotal = sum((item.subtotal for item in invoice.items), Decimal("0"))
    discounted = subtotal * (Decimal("1") - invoice.discount_pct / Decimal("100"))
    taxed = discounted * (Decimal("1") + Decimal(str(tax_rate)))
    return taxed.quantize(CENT, rounding=ROUND_HALF_UP)


def finalize(invoice: Invoice) -> Invoice:
    if not invoice.items:
        raise ValueError("cannot finalize an empty invoice")
    invoice.status = "open"
    return invoice
