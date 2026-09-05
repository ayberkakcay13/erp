"""Pydantic request/response modelleri (Pydantic v2)."""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------- Customer ----------------

class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


# ---------------- Product ----------------

class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str = Field(min_length=1, max_length=50)
    price: float = Field(ge=0)
    stock: int = Field(default=0, ge=0)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sku: Optional[str] = Field(default=None, min_length=1, max_length=50)
    price: Optional[float] = Field(default=None, ge=0)
    stock: Optional[int] = Field(default=None, ge=0)


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


# ---------------- SalesItem ----------------

class SalesItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)


class SalesItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    unit_price: float
    total_price: float
    product_name: Optional[str] = None
    product_sku: Optional[str] = None


# ---------------- Sale ----------------

class SaleCreate(BaseModel):
    customer_id: int
    sale_date: Optional[date] = None
    items: List[SalesItemCreate] = Field(min_length=1)


class SaleStatusUpdate(BaseModel):
    status: str = Field(pattern='^(pending|completed|cancelled)$')


class SaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    sale_date: date
    total_amount: float
    status: str
    created_at: Optional[datetime] = None
    customer: Optional[CustomerResponse] = None
    items: List[SalesItemResponse] = []


# ---------------- Invoice ----------------

class InvoiceCreate(BaseModel):
    """POST /api/sales/{sale_id}/invoice govdesi - hepsi opsiyonel."""
    issued_date: Optional[date] = None
    tax_rate: float = Field(default=0.0, ge=0, le=1, description='0.20 = %20 KDV')


class InvoiceStatusUpdate(BaseModel):
    status: str = Field(pattern='^(draft|issued|paid)$')


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_id: int
    invoice_number: str
    customer_id: int
    issued_date: date
    total_amount: float
    status: str
    created_at: Optional[datetime] = None
