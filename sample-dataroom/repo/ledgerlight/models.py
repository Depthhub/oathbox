from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class LineItem:
    description: str
    quantity: int
    unit_price: Decimal

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class Invoice:
    customer_id: str
    currency: str
    items: list[LineItem] = field(default_factory=list)
    discount_pct: Decimal = Decimal("0")
    status: str = "draft"
