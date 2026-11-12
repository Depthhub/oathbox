"""In-memory invoice store. Production uses Postgres (see infra repo)."""

import uuid

from .models import Invoice

_INVOICES: dict[str, Invoice] = {}


def save(invoice: Invoice) -> str:
    invoice_id = f"inv_{uuid.uuid4().hex[:12]}"
    _INVOICES[invoice_id] = invoice
    return invoice_id


def get(invoice_id: str) -> Invoice | None:
    return _INVOICES.get(invoice_id)


def count_open() -> int:
    return sum(1 for inv in _INVOICES.values() if inv.status == "open")
