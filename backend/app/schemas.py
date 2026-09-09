"""Pydantic request/response modelleri (Pydantic v2)."""
from datetime import date, datetime
from decimal import Decimal
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
    price: Decimal = Field(ge=0)
    # --- Phase 13: urun karti ---
    stock_uom_id: Optional[int] = None
    purchase_uom_id: Optional[int] = None
    sales_uom_id: Optional[int] = None
    item_group_id: Optional[int] = None
    brand_id: Optional[int] = None
    product_type: str = Field(default='stoklu', pattern='^(stoklu|hizmet|sarf)$')
    is_active: bool = True
    description: Optional[str] = None
    image_url: Optional[str] = Field(default=None, max_length=500)
    min_stock_level: Optional[Decimal] = Field(default=None, ge=0)
    max_stock_level: Optional[Decimal] = Field(default=None, ge=0)
    is_variant_template: bool = False
    parent_product_id: Optional[int] = None


class ProductCreate(ProductBase):
    """`stock` artik urunun kolonu degil, acilis stok hareketi (Phase 10).

    Verilirse `reason='acilis'` ile varsayilan (ya da secilen) depoya
    ledger kaydi atilir. `stock_entry_uom_id` verilirse miktar once urunun
    stok birimine cevrilir (Phase 13).
    """
    stock: Decimal = Field(default=Decimal('0'), ge=0)
    warehouse_id: Optional[int] = None
    stock_entry_uom_id: Optional[int] = None
    barcodes: List['ProductBarcodeCreate'] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sku: Optional[str] = Field(default=None, min_length=1, max_length=50)
    price: Optional[Decimal] = Field(default=None, ge=0)
    # Stok dogrudan yazilmaz; verilirse fark kadar `duzeltme` hareketi atilir.
    stock: Optional[Decimal] = Field(default=None, ge=0)
    warehouse_id: Optional[int] = None
    stock_uom_id: Optional[int] = None
    purchase_uom_id: Optional[int] = None
    sales_uom_id: Optional[int] = None
    item_group_id: Optional[int] = None
    brand_id: Optional[int] = None
    product_type: Optional[str] = Field(default=None, pattern='^(stoklu|hizmet|sarf)$')
    is_active: Optional[bool] = None
    description: Optional[str] = None
    image_url: Optional[str] = Field(default=None, max_length=500)
    min_stock_level: Optional[Decimal] = Field(default=None, ge=0)
    max_stock_level: Optional[Decimal] = Field(default=None, ge=0)
    is_variant_template: Optional[bool] = None


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None
    # Ledger toplamindan hesaplanir, tabloda kolon degildir.
    stock: Decimal = Decimal('0')
    stock_uom_code: Optional[str] = None
    item_group_name: Optional[str] = None
    brand_name: Optional[str] = None
    barcodes: List['ProductBarcodeResponse'] = []


# ---------------- SalesItem ----------------

class SalesItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    warehouse_id: Optional[int] = None
    # Phase 13: farkli birimde satis. Ledger'a yazilirken stok birimine cevrilir.
    uom_id: Optional[int] = None


class SalesItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal
    warehouse_id: Optional[int] = None
    uom_id: Optional[int] = None
    stock_quantity: Optional[Decimal] = None
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    warehouse_name: Optional[str] = None
    uom_code: Optional[str] = None


# ---------------- Sale ----------------

class SaleCreate(BaseModel):
    customer_id: int
    sale_date: Optional[date] = None
    items: List[SalesItemCreate] = Field(min_length=1)
    # Phase 11: varsayilan davranis "olustur ve onayla" (stok hareketi olusur).
    # true verilirse belge taslak kalir, stok hareketi onaya kadar yazilmaz.
    save_as_draft: bool = False


class SaleStatusUpdate(BaseModel):
    status: str = Field(pattern='^(pending|completed|cancelled)$')


class SaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    sale_date: date
    total_amount: Decimal
    status: str
    docstatus: int = 0
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[int] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[int] = None
    cancel_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    customer: Optional[CustomerResponse] = None
    items: List[SalesItemResponse] = []


# ---------------- Invoice ----------------

class InvoiceCreate(BaseModel):
    """POST /api/sales/{sale_id}/invoice govdesi - hepsi opsiyonel."""
    issued_date: Optional[date] = None
    tax_rate: Decimal = Field(default=Decimal('0'), ge=0, le=1, description='0.20 = %20 KDV')
    # Phase 11: taslak fatura numara almaz; numara onay aninda atanir
    save_as_draft: bool = False


class InvoiceStatusUpdate(BaseModel):
    status: str = Field(pattern='^(draft|issued|paid)$')


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_id: int
    invoice_number: Optional[str] = None
    customer_id: int
    issued_date: date
    total_amount: Decimal
    status: str
    docstatus: int = 0
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[int] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[int] = None
    cancel_reason: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------- User / Auth ----------------

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=255)


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default='sales', pattern='^(admin|sales)$')


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    """Sifre alanlari BILEREK yok - disari asla sizmamali."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    is_active: bool
    created_at: Optional[datetime] = None


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: UserResponse


# ---------------- Phase 10: Depo / Stok Defteri / Transfer ----------------

WAREHOUSE_TYPE_PATTERN = '^(merkez|sube|arac|iade|karantina)$'
STOCK_REASON_PATTERN = (
    '^(acilis|satis|satis_iptal|alim|alim_iade|transfer_giris|transfer_cikis'
    '|sayim|fire|duzeltme)$'
)


class WarehouseBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    warehouse_type: str = Field(default='merkez', pattern=WAREHOUSE_TYPE_PATTERN)
    parent_id: Optional[int] = None
    is_active: bool = True
    is_default: bool = False


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    warehouse_type: Optional[str] = Field(default=None, pattern=WAREHOUSE_TYPE_PATTERN)
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class WarehouseResponse(WarehouseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


class StockLedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    warehouse_id: int
    change_qty: Decimal
    balance_qty: Decimal
    reason: str
    ref_type: Optional[str] = None
    ref_id: Optional[int] = None
    note: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    warehouse_name: Optional[str] = None


class StockBalanceRow(BaseModel):
    product_id: int
    product_name: str
    sku: str
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    quantity: Decimal


class StockAdjustment(BaseModel):
    """Elle stok duzeltme / sayim girisi."""
    product_id: int
    warehouse_id: Optional[int] = None
    change_qty: Decimal = Field()
    reason: str = Field(default='duzeltme', pattern=STOCK_REASON_PATTERN)
    note: Optional[str] = None


class StockTransferItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)


class StockTransferItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: Decimal
    product_name: Optional[str] = None
    product_sku: Optional[str] = None


class StockTransferCreate(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    transfer_date: Optional[date] = None
    note: Optional[str] = None
    items: List[StockTransferItemCreate] = Field(min_length=1)
    # Phase 11: varsayilan "olustur ve onayla"; taslak transfer stok hareketi yazmaz
    save_as_draft: bool = False


class StockTransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transfer_no: str
    from_warehouse_id: int
    to_warehouse_id: int
    transfer_date: date
    status: str
    docstatus: int = 0
    docstatus_label: Optional[str] = None
    cancel_reason: Optional[str] = None
    note: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    from_warehouse_name: Optional[str] = None
    to_warehouse_name: Optional[str] = None
    items: List[StockTransferItemResponse] = []


# ---------------- Phase 11: Belge durumu / numaralandirma / denetim izi ----------------

DOCSTATUS_LABELS = {0: 'taslak', 1: 'onayli', 2: 'iptal'}


class DocumentStatusFields(BaseModel):
    """Belge yasam dongusu alanlari - response modellerine karistirilir."""
    docstatus: int = 0
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[int] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[int] = None
    cancel_reason: Optional[str] = None


class CancelRequest(BaseModel):
    """Iptal isleminde sebep sorulur."""
    reason: Optional[str] = Field(default=None, max_length=500)


class NamingSeriesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_type: str
    prefix: str
    year: int
    current_number: int
    padding: int
    tenant_id: Optional[int] = None
    next_number: Optional[str] = None
    created_at: Optional[datetime] = None


class NamingSeriesUpdate(BaseModel):
    """Sadece admin. current_number geriye alinamaz - numara tekrari olusur."""
    prefix: Optional[str] = Field(default=None, min_length=1, max_length=20)
    padding: Optional[int] = Field(default=None, ge=1, le=12)
    current_number: Optional[int] = Field(default=None, ge=0)


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_name: str
    record_id: Optional[int] = None
    action: str
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------- Phase 12: Cok kiracili mimari ----------------

class TenantModuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_code: str
    is_enabled: bool


class TenantBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=63, pattern='^[a-z0-9][a-z0-9-]*$')
    tax_number: Optional[str] = Field(default=None, max_length=20)
    plan: str = Field(default='free', pattern='^(free|basic|pro)$')


class TenantCreate(TenantBase):
    """Yeni firma acar. Yonetici bilgisi verilirse ilk admin de olusturulur."""
    modules: Optional[List[str]] = None
    admin_email: Optional[EmailStr] = None
    admin_password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    admin_full_name: Optional[str] = Field(default=None, max_length=255)


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=63,
                                pattern='^[a-z0-9][a-z0-9-]*$')
    tax_number: Optional[str] = Field(default=None, max_length=20)
    plan: Optional[str] = Field(default=None, pattern='^(free|basic|pro)$')
    is_active: Optional[bool] = None


class TenantModuleUpdate(BaseModel):
    """Gonderilen liste ACIK modullerdir; listede olmayanlar kapatilir."""
    modules: List[str] = Field(default_factory=list)


class TenantResponse(TenantBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool = True
    created_at: Optional[datetime] = None
    modules: List[TenantModuleResponse] = []


# ---------------- Phase 13: Olcu birimi, kategori, urun yapisi ----------------

PRODUCT_TYPE_PATTERN = '^(stoklu|hizmet|sarf)$'
BARCODE_TYPE_PATTERN = '^(EAN13|EAN8|CODE128|QR)$'


class UOMBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=50)
    is_integer: bool = False
    is_active: bool = True


class UOMCreate(UOMBase):
    pass


class UOMUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    is_integer: Optional[bool] = None
    is_active: Optional[bool] = None


class UOMResponse(UOMBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


class UOMConversionCreate(BaseModel):
    """product_id verilirse o urune ozel donusum olur ve geneli ezer."""
    from_uom_id: int
    to_uom_id: int
    factor: Decimal = Field(gt=0)
    product_id: Optional[int] = None


class UOMConversionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_uom_id: int
    to_uom_id: int
    factor: Decimal
    product_id: Optional[int] = None
    from_uom_code: Optional[str] = None
    to_uom_code: Optional[str] = None


class ItemGroupBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    parent_id: Optional[int] = None
    is_active: bool = True


class ItemGroupCreate(ItemGroupBase):
    pass


class ItemGroupUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None


class ItemGroupResponse(ItemGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


class BrandBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class BrandCreate(BrandBase):
    pass


class BrandUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_active: Optional[bool] = None


class BrandResponse(BrandBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


class ProductBarcodeCreate(BaseModel):
    barcode: str = Field(min_length=1, max_length=64)
    barcode_type: str = Field(default='EAN13', pattern=BARCODE_TYPE_PATTERN)
    uom_id: Optional[int] = None
    is_primary: bool = False


class ProductBarcodeResponse(ProductBarcodeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int


class ItemAttributeValueCreate(BaseModel):
    value: str = Field(min_length=1, max_length=100)
    sort_order: int = 0


class ItemAttributeValueResponse(ItemAttributeValueCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attribute_id: int


class ItemAttributeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    values: List[ItemAttributeValueCreate] = Field(default_factory=list)


class ItemAttributeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    values: List[ItemAttributeValueResponse] = []


class GenerateVariantsRequest(BaseModel):
    """Secilen ozniteliklerin kombinasyonundan varyant urunler uretir."""
    attribute_ids: List[int] = Field(min_length=1)
    value_ids: Optional[List[int]] = None


# ProductCreate/ProductResponse, asagida tanimlanan barkod semalarina
# atif yapiyor; ileri referanslari burada cozuyoruz.
ProductCreate.model_rebuild()
ProductResponse.model_rebuild()
