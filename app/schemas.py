from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["draft", "sent", "paid", "overdue"]


class InvoiceCreate(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=50)
    customer_name: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    status: Status = "draft"


class InvoiceUpdate(BaseModel):
    """All fields optional: PATCH changes only what is sent."""
    customer_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    amount: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    status: Optional[Status] = None


class InvoiceOut(InvoiceCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
