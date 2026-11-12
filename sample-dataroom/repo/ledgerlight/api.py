from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import billing, store
from .config import DEFAULT_CURRENCY
from .models import Invoice, LineItem

app = FastAPI(title="Ledgerlight")


class LineItemIn(BaseModel):
    description: str
    quantity: int
    unit_price: Decimal


class InvoiceIn(BaseModel):
    customer_id: str
    items: list[LineItemIn]
    discount_pct: Decimal = Decimal("0")


@app.post("/invoices")
def create_invoice(body: InvoiceIn) -> dict:
    invoice = Invoice(
        customer_id=body.customer_id,
        currency=DEFAULT_CURRENCY,
        items=[LineItem(i.description, i.quantity, i.unit_price) for i in body.items],
        discount_pct=body.discount_pct,
    )
    billing.finalize(invoice)
    invoice_id = store.save(invoice)
    return {"id": invoice_id, "total": str(billing.invoice_total(invoice))}


@app.get("/invoices/{invoice_id}")
def read_invoice(invoice_id: str) -> dict:
    invoice = store.get(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": invoice.status, "total": str(billing.invoice_total(invoice))}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8081)
