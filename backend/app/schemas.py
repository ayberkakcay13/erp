"""Pydantic request/response modelleri (Pydantic v2)."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------------- Customer ----------------

class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)


class CustomerCreate(CustomerBase):
    # Phase 15: kredi limiti (0 = limitsiz) ve vade gun sayisi
    credit_limit: Decimal = Field(default=Decimal('0'), ge=0)
    credit_days: int = Field(default=0, ge=0, le=365)


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    credit_limit: Optional[Decimal] = Field(default=None, ge=0)
    credit_days: Optional[int] = Field(default=None, ge=0, le=365)


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    credit_limit: Decimal = Decimal('0')
    credit_days: int = 0
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
    # Phase 15: siparis kaleminde KDV orani (yuzde)
    tax_rate: Decimal = Field(default=Decimal('0'), ge=0, le=100)


class SalesItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal = Decimal('0')
    total_price: Decimal
    warehouse_id: Optional[int] = None
    uom_id: Optional[int] = None
    stock_quantity: Optional[Decimal] = None
    delivered_quantity: Decimal = Decimal('0')
    remaining_quantity: Optional[Decimal] = None
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    warehouse_name: Optional[str] = None
    uom_code: Optional[str] = None


# ---------------- Sale ----------------

class SaleCreate(BaseModel):
    customer_id: int
    sale_date: Optional[date] = None
    warehouse_id: Optional[int] = None
    items: List[SalesItemCreate] = Field(min_length=1)
    # Phase 11: varsayilan davranis "olustur ve onayla" (stok hareketi olusur).
    # true verilirse belge taslak kalir, stok hareketi onaya kadar yazilmaz.
    save_as_draft: bool = False
    # Phase 15: kredi limiti asilsa bile devam et (uyari yine de doner)
    block_if_credit_exceeded: bool = False


class SaleStatusUpdate(BaseModel):
    status: str = Field(pattern='^(pending|completed|cancelled)$')


class SaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    sale_date: date
    so_number: Optional[str] = None
    warehouse_id: Optional[int] = None
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
    # Phase 15: kredi limiti asildiginda uyari (engellemez, bilgi amacli)
    credit_warning: Optional[dict] = None


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
    # Phase 15: kalemli fatura satistan bagimsiz da olusabilir (sale_id yok)
    sale_id: Optional[int] = None
    delivery_note_id: Optional[int] = None
    invoice_number: Optional[str] = None
    customer_id: int
    issued_date: date
    due_date: Optional[date] = None
    subtotal: Optional[Decimal] = None
    tax_total: Optional[Decimal] = None
    total_amount: Decimal
    status: str
    payment_status: str = 'odenmedi'
    docstatus: int = 0
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[int] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[int] = None
    cancel_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    items: List['InvoiceItemResponse'] = []


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


# ---------------- Phase 14: Tedarikci ve satin alma ----------------

class SupplierBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    tax_number: Optional[str] = Field(default=None, min_length=10, max_length=11)
    tax_office: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(default=None, max_length=100)
    contact_person: Optional[str] = Field(default=None, max_length=255)
    payment_term_days: int = Field(default=0, ge=0, le=365)
    is_active: bool = True

    @field_validator('tax_number')
    @classmethod
    def check_tax_number(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            return None
        if not value.isdigit() or len(value) not in (10, 11):
            raise ValueError('VKN 10, TCKN 11 haneli rakam olmali')
        return value


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tax_number: Optional[str] = Field(default=None, min_length=10, max_length=11)
    tax_office: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(default=None, max_length=100)
    contact_person: Optional[str] = Field(default=None, max_length=255)
    payment_term_days: Optional[int] = Field(default=None, ge=0, le=365)
    is_active: Optional[bool] = None

    _check_tax_number = field_validator('tax_number')(
        SupplierBase.check_tax_number.__func__
    )


class SupplierResponse(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


class PurchaseOrderItemCreate(BaseModel):
    product_id: int
    uom_id: Optional[int] = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal('0'), ge=0, le=100)


class PurchaseOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    uom_id: Optional[int] = None
    uom_code: Optional[str] = None
    quantity: Decimal
    received_quantity: Decimal
    remaining_quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    order_date: Optional[date] = None
    expected_date: Optional[date] = None
    warehouse_id: Optional[int] = None
    note: Optional[str] = None
    save_as_draft: bool = False
    items: List[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderUpdate(BaseModel):
    supplier_id: Optional[int] = None
    order_date: Optional[date] = None
    expected_date: Optional[date] = None
    warehouse_id: Optional[int] = None
    note: Optional[str] = None
    items: Optional[List[PurchaseOrderItemCreate]] = None


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    po_number: Optional[str] = None
    supplier_id: int
    supplier_name: Optional[str] = None
    order_date: date
    expected_date: Optional[date] = None
    warehouse_id: Optional[int] = None
    status: str
    docstatus: int
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    items: List[PurchaseOrderItemResponse] = []


class PurchaseReceiptItemCreate(BaseModel):
    product_id: int
    purchase_order_item_id: Optional[int] = None
    uom_id: Optional[int] = None
    quantity: Decimal = Field(gt=0)
    accepted_quantity: Optional[Decimal] = Field(default=None, ge=0)
    rejected_quantity: Decimal = Field(default=Decimal('0'), ge=0)
    unit_price: Decimal = Field(default=Decimal('0'), ge=0)
    reject_reason: Optional[str] = None


class PurchaseReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    purchase_order_item_id: Optional[int] = None
    uom_id: Optional[int] = None
    uom_code: Optional[str] = None
    quantity: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal
    stock_quantity: Optional[Decimal] = None
    unit_price: Decimal
    reject_reason: Optional[str] = None


class PurchaseReceiptCreate(BaseModel):
    supplier_id: int
    purchase_order_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    receipt_date: Optional[date] = None
    note: Optional[str] = None
    save_as_draft: bool = False
    items: List[PurchaseReceiptItemCreate] = Field(min_length=1)


class PurchaseReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: Optional[str] = None
    purchase_order_id: Optional[int] = None
    po_number: Optional[str] = None
    supplier_id: int
    supplier_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    receipt_date: date
    docstatus: int
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    items: List[PurchaseReceiptItemResponse] = []


class PurchaseInvoiceItemCreate(BaseModel):
    product_id: int
    uom_id: Optional[int] = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal('0'), ge=0, le=100)


class PurchaseInvoiceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    uom_id: Optional[int] = None
    uom_code: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


class PurchaseInvoiceCreate(BaseModel):
    supplier_id: int
    invoice_number: str = Field(min_length=1, max_length=50)
    purchase_receipt_id: Optional[int] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    note: Optional[str] = None
    save_as_draft: bool = False
    items: List[PurchaseInvoiceItemCreate] = Field(min_length=1)


class PurchaseInvoiceUpdate(BaseModel):
    invoice_number: Optional[str] = Field(default=None, min_length=1, max_length=50)
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    payment_status: Optional[str] = None
    note: Optional[str] = None
    items: Optional[List[PurchaseInvoiceItemCreate]] = None


class PurchaseInvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: str
    internal_number: Optional[str] = None
    supplier_id: int
    supplier_name: Optional[str] = None
    purchase_receipt_id: Optional[int] = None
    receipt_number: Optional[str] = None
    invoice_date: date
    due_date: Optional[date] = None
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    payment_status: str
    docstatus: int
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    items: List[PurchaseInvoiceItemResponse] = []


class PurchaseMatchRow(BaseModel):
    product_id: int
    product_name: Optional[str] = None
    uom_id: Optional[int] = None
    ordered_quantity: Decimal
    received_quantity: Decimal
    invoiced_quantity: Decimal
    order_unit_price: Decimal
    receipt_unit_price: Optional[Decimal] = None
    invoice_unit_price: Optional[Decimal] = None
    quantity_difference: bool
    price_difference: bool


class PurchaseMatchResponse(BaseModel):
    purchase_order_id: int
    po_number: Optional[str] = None
    status: str
    has_difference: bool
    rows: List[PurchaseMatchRow] = []


# ---------------- Phase 15: Teklif, Siparis, Sevkiyat, Kredi ----------------

class QuotationItemCreate(BaseModel):
    product_id: int
    uom_id: Optional[int] = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal('0'), ge=0, le=100)


class QuotationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    uom_id: Optional[int] = None
    uom_code: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    total_price: Decimal


class QuotationCreate(BaseModel):
    customer_id: int
    quotation_date: Optional[date] = None
    valid_until: Optional[date] = None
    note: Optional[str] = None
    save_as_draft: bool = False
    items: List[QuotationItemCreate] = Field(min_length=1)


class QuotationUpdate(BaseModel):
    valid_until: Optional[date] = None
    note: Optional[str] = None
    items: Optional[List[QuotationItemCreate]] = None


class QuotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quotation_number: Optional[str] = None
    customer_id: int
    customer_name: Optional[str] = None
    quotation_date: date
    valid_until: Optional[date] = None
    status: str
    docstatus: int
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    subtotal: Decimal
    tax_total: Decimal
    total_amount: Decimal
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    items: List[QuotationItemResponse] = []


class QuotationToSalesOrderRequest(BaseModel):
    """Teklifi siparise cevirir. warehouse_id/promised_delivery_date opsiyonel."""
    warehouse_id: Optional[int] = None
    promised_delivery_date: Optional[date] = None
    save_as_draft: bool = False


# ---------------- SalesOrder (dedicated router - /api/sales-orders) ----------------

class SalesOrderCreate(SaleCreate):
    quotation_id: Optional[int] = None
    promised_delivery_date: Optional[date] = None


class SalesOrderResponse(SaleResponse):
    quotation_id: Optional[int] = None
    promised_delivery_date: Optional[date] = None
    subtotal: Optional[Decimal] = None
    tax_total: Optional[Decimal] = None


# ---------------- DeliveryNote ----------------

class DeliveryNoteItemCreate(BaseModel):
    product_id: int
    sales_order_item_id: Optional[int] = None
    uom_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(default=Decimal('0'), ge=0)
    item_status: str = Field(default='hazirlanan')


class DeliveryNoteItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    sales_order_item_id: Optional[int] = None
    uom_id: Optional[int] = None
    uom_code: Optional[str] = None
    warehouse_id: Optional[int] = None
    quantity: Decimal
    stock_quantity: Optional[Decimal] = None
    unit_price: Decimal
    item_status: str


class DeliveryNoteCreate(BaseModel):
    sales_order_id: Optional[int] = None
    customer_id: int
    warehouse_id: Optional[int] = None
    delivery_date: Optional[date] = None
    note: Optional[str] = None
    save_as_draft: bool = False
    items: List[DeliveryNoteItemCreate] = Field(min_length=1)


class DeliveryNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    delivery_note_number: Optional[str] = None
    sales_order_id: Optional[int] = None
    so_number: Optional[str] = None
    customer_id: int
    customer_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    delivery_date: date
    docstatus: int
    docstatus_label: Optional[str] = None
    submitted_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    items: List[DeliveryNoteItemResponse] = []


# ---------------- Invoice (kalemli, Phase 15) ----------------

class InvoiceItemCreate(BaseModel):
    product_id: int
    uom_id: Optional[int] = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal('0'), ge=0, le=100)


class InvoiceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    uom_id: Optional[int] = None
    uom_code: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    total_price: Decimal


class InvoiceCreateV2(BaseModel):
    """POST /api/invoices - kalemli fatura, satistan bagimsiz olusturulabilir."""
    customer_id: int
    delivery_note_id: Optional[int] = None
    issued_date: Optional[date] = None
    due_date: Optional[date] = None
    note: Optional[str] = None
    save_as_draft: bool = False
    items: List[InvoiceItemCreate] = Field(min_length=1)


class InvoiceUpdate(BaseModel):
    payment_status: Optional[str] = None
    due_date: Optional[date] = None


# ---------------- Kredi limiti ----------------

class CustomerCreditUpdate(BaseModel):
    credit_limit: Decimal = Field(ge=0)
    credit_days: int = Field(default=0, ge=0, le=365)


class CreditCheckResponse(BaseModel):
    allowed: bool
    credit_limit: Decimal
    credit_used: Decimal
    available: Optional[Decimal] = None
    requested: Decimal
    message: Optional[str] = None


class CustomerCreditSummary(BaseModel):
    customer_id: int
    customer_name: str
    credit_limit: Decimal
    credit_used: Decimal
    available: Optional[Decimal] = None
    credit_days: int


InvoiceResponse.model_rebuild()
