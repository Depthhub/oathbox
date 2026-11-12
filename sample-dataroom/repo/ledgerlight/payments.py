import httpx

from .config import PAYMENTS_API_KEY, PAYMENTS_BASE_URL
from .models import Invoice


def create_payment_link(invoice: Invoice, amount_cents: int) -> str:
    response = httpx.post(
        f"{PAYMENTS_BASE_URL}/links",
        headers={"Authorization": f"Bearer {PAYMENTS_API_KEY}"},
        json={
            "customer": invoice.customer_id,
            "amount": amount_cents,
            "currency": invoice.currency,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["url"]
