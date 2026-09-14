from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy import event
from sqlalchemy.orm import declared_attr, relationship
from .database import Base
from datetime import datetime
# ---------------- Phase 12: Cok kiracili mimari ----------------
# Izolasyon satir bazli (`tenant_id`) + PostgreSQL Row Level Security ile
# saglanir. Uygulama katmaninda WHERE unutulsa bile RLS satiri dondurmez.

MODULE_CODES = (
    'sales', 'purchase', 'stock', 'invoice', 'reports',
    'manufacturing', 'payroll', 'accounting', 'efatura',
)

# Yeni bir tenant acilirken varsayilan olarak acik gelen modüller
DEFAULT_ENABLED_MODULES = ('sales', 'purchase', 'stock', 'invoice', 'reports')

TENANT_PLANS = ('free', 'basic', 'pro')


class TenantMixin:
    """tenant_id kolonunu ve indexini tek yerden verir.

    Yeni bir is tablosu eklerken bu mixin'i kullan; RLS migration'i
    `tenant_id` tasiyan tum tablolari otomatik bulur.
    """

    @declared_attr
    def tenant_id(cls):  # noqa: N805
        return Column(
            Integer,
            ForeignKey('tenants.id'),
            nullable=True,  # migration sonrasi NOT NULL'a cekilir
            index=True,
        )


class Tenant(Base):
    __tablename__ = 'tenants'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(63), unique=True, nullable=False)  # subdomain
    tax_number = Column(String(20), nullable=True)  # VKN
    is_active = Column(Boolean, nullable=False, default=True)
    plan = Column(String(20), nullable=False, default='free')
    created_at = Column(DateTime, default=datetime.utcnow)

    modules = relationship(
        'TenantModule', back_populates='tenant', cascade='all, delete-orphan'
    )


class TenantModule(Base):
    __tablename__ = 'tenant_modules'
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('tenants.id'), nullable=False, index=True)
    module_code = Column(String(30), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)

    tenant = relationship('Tenant', back_populates='modules')

    __table_args__ = (
        UniqueConstraint('tenant_id', 'module_code', name='uq_tenant_module'),
    )



class Customer(TenantMixin, Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    # Phase 12: e-posta artik TENANT ICINDE tekil - iki firma ayni musteriyle calisabilir
    email = Column(String(255), nullable=False)
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    credit_limit = Column(Numeric(18, 4), nullable=False, default=0)
    credit_days = Column(Integer, nullable=False, default=0)
    sales = relationship(
        'SalesOrder', back_populates='customer', cascade='all, delete-orphan'
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'email', name='uq_customers_tenant_email'),
    )

class Product(TenantMixin, Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    # Phase 12: urun kodu TENANT ICINDE tekil, global degil
    sku = Column(String(50), nullable=False)
    price = Column(Numeric(18, 4), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # --- Phase 13: urun karti ---
    # Stok DAIMA stock_uom cinsinden tutulur; alim/satis farkli birimdeyse
    # ledger'a yazmadan once uom_service.convert() ile bu birime cevrilir.
    stock_uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    purchase_uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    sales_uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    item_group_id = Column(Integer, ForeignKey('item_groups.id'), nullable=True)
    brand_id = Column(Integer, ForeignKey('brands.id'), nullable=True)
    # hizmet urunu stok tutmaz
    product_type = Column(String(20), nullable=False, default='stoklu')
    is_active = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    # Phase 26'da kullanilacak, simdilik alan olarak duruyor
    min_stock_level = Column(Numeric(18, 4), nullable=True)
    max_stock_level = Column(Numeric(18, 4), nullable=True)
    # Varyant sistemi: sablon urun stok TUTMAZ, stok varyantlarda durur
    is_variant_template = Column(Boolean, nullable=False, default=False)
    parent_product_id = Column(Integer, ForeignKey('products.id'), nullable=True)

    sales_items = relationship('SalesOrderItem', back_populates='product')
    stock_uom = relationship('UOM', foreign_keys=[stock_uom_id])
    purchase_uom = relationship('UOM', foreign_keys=[purchase_uom_id])
    sales_uom = relationship('UOM', foreign_keys=[sales_uom_id])
    item_group = relationship('ItemGroup')
    brand = relationship('Brand')
    barcodes = relationship(
        'ProductBarcode', back_populates='product', cascade='all, delete-orphan'
    )
    # remote_side=[id] -> bu taraf "cocuk", karsi taraf "sablon".
    # backref sayesinde sablon urunun varyantlari product.variants ile gelir.
    template = relationship(
        'Product', remote_side=[id], foreign_keys=[parent_product_id],
        backref='variants',
    )
    variant_attributes = relationship(
        'ProductVariantAttribute',
        primaryjoin='Product.id == ProductVariantAttribute.product_id',
        cascade='all, delete-orphan',
        viewonly=False,
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'sku', name='uq_products_tenant_sku'),
    )

class SalesOrder(TenantMixin, Base):
    """Satis siparisi (Phase 15 - eski Sale'in yerini alir, ayni tablo id'leri).

    Onayi STOK HAREKETI YARATMAZ - niyet beyanidir. Stok yalnizca DeliveryNote
    onayinda hareket eder (bkz. document_service._delivery_stock_entries).
    """
    __tablename__ = 'sales_orders'
    id = Column(Integer, primary_key=True)
    so_number = Column(String(50), nullable=True)
    quotation_id = Column(Integer, ForeignKey('quotations.id'), nullable=True)
    # Phase 19: musteri detay modal'i customer_id + sale_date ile filtreler/gruplar
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    sale_date = Column(Date, nullable=False, index=True)
    promised_delivery_date = Column(Date, nullable=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    subtotal = Column(Numeric(18, 4), nullable=True)
    tax_total = Column(Numeric(18, 4), nullable=True)
    total_amount = Column(Numeric(18, 4), nullable=False)
    # draft|pending|confirmed|partially_delivered|delivered|completed|cancelled
    # (pending/completed eski Sale uyum degerleri; SalesOrder bunlari da kabul eder)
    status = Column(String(20), default='pending')
    # Phase 11: belge yasam dongusu (status is durumu icin ayri kalir)
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    customer = relationship('Customer', back_populates='sales')
    quotation = relationship('Quotation')
    warehouse = relationship('Warehouse')
    items = relationship(
        'SalesOrderItem', back_populates='sales_order', cascade='all, delete-orphan'
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'so_number', name='uq_sales_order_tenant_number'),
    )


class SalesOrderItem(TenantMixin, Base):
    """Siparis kalemi (Phase 15 - eski SalesItem, ayni tablo id'leri)."""
    __tablename__ = 'sales_order_items'
    id = Column(Integer, primary_key=True)
    sales_order_id = Column(Integer, ForeignKey('sales_orders.id'), nullable=False, index=True)
    # Phase 19: urun detay modal'i bu kolonla filtreler
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    tax_rate = Column(Numeric(18, 4), nullable=False, default=0)
    total_price = Column(Numeric(18, 4), nullable=False)
    # Phase 10: satis kalemi hangi depodan cikti (bossa varsayilan depo)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    # Phase 13: `quantity` musterinin girdigi birimde (fiyat da o birimde),
    # `stock_quantity` ise stok birimine cevrilmis hali - ledger bunu kullanir.
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    stock_quantity = Column(Numeric(18, 4), nullable=True)
    # Phase 15: DeliveryNote onaylandikca artar - kismi sevkiyat hesabinin temeli
    delivered_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    sales_order = relationship('SalesOrder', back_populates='items')
    product = relationship('Product', back_populates='sales_items')
    uom = relationship('UOM')


# Phase 10-14 kodu ve testleri Sale/SalesItem adiyla import ediyor;
# Phase 15 tablo adini degistirdi ama sinif kimligini korumak icin alias.
Sale = SalesOrder
SalesItem = SalesOrderItem


class Quotation(TenantMixin, Base):
    """Teklif (Phase 15). Opsiyonel - SalesOrder dogrudan da acilabilir."""
    __tablename__ = 'quotations'
    id = Column(Integer, primary_key=True)
    quotation_number = Column(String(50), nullable=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    quotation_date = Column(Date, nullable=False, default=datetime.utcnow)
    valid_until = Column(Date, nullable=True)
    # taslak|gonderildi|kabul|red
    status = Column(String(20), nullable=False, default='taslak')
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    subtotal = Column(Numeric(18, 4), nullable=False, default=0)
    tax_total = Column(Numeric(18, 4), nullable=False, default=0)
    total_amount = Column(Numeric(18, 4), nullable=False, default=0)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship('Customer')
    items = relationship(
        'QuotationItem', back_populates='quotation', cascade='all, delete-orphan'
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'quotation_number', name='uq_quotation_tenant_number'),
    )


class QuotationItem(TenantMixin, Base):
    __tablename__ = 'quotation_items'
    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey('quotations.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    tax_rate = Column(Numeric(18, 4), nullable=False, default=0)
    total_price = Column(Numeric(18, 4), nullable=False)

    quotation = relationship('Quotation', back_populates='items')
    product = relationship('Product')
    uom = relationship('UOM')


class DeliveryNote(TenantMixin, Base):
    """Sevkiyat irsaliyesi (Phase 15). STOK HAREKETI BURADA olusur.

    Onayla (docstatus=1) HER KALEM icin stock_service.add_entry(reason='satis',
    ref_type='delivery', ref_id=delivery_note.id) cagrilir.
    """
    __tablename__ = 'delivery_notes'
    id = Column(Integer, primary_key=True)
    delivery_note_number = Column(String(50), nullable=True)
    sales_order_id = Column(Integer, ForeignKey('sales_orders.id'), nullable=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    delivery_date = Column(Date, nullable=False, default=datetime.utcnow)
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sales_order = relationship('SalesOrder')
    customer = relationship('Customer')
    warehouse = relationship('Warehouse')
    items = relationship(
        'DeliveryNoteItem', back_populates='delivery_note', cascade='all, delete-orphan'
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'delivery_note_number', name='uq_dn_tenant_number'),
    )


class DeliveryNoteItem(TenantMixin, Base):
    __tablename__ = 'delivery_note_items'
    id = Column(Integer, primary_key=True)
    delivery_note_id = Column(Integer, ForeignKey('delivery_notes.id'), nullable=False)
    sales_order_item_id = Column(Integer, ForeignKey('sales_order_items.id'), nullable=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False, default=0)
    # Kalem bossa DeliveryNote.warehouse_id kullanilir - Phase 10 kalitindan
    # (satis kalemi hangi depodan cikti) uyum icin
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    # Phase 13 kurali: ledger'a yazilan miktar her zaman stok biriminde
    stock_quantity = Column(Numeric(18, 4), nullable=True)
    # hazirlanan|paketlendi|sevk_edildi
    item_status = Column(String(20), nullable=False, default='hazirlanan')

    delivery_note = relationship('DeliveryNote', back_populates='items')
    sales_order_item = relationship('SalesOrderItem')
    product = relationship('Product')
    uom = relationship('UOM')


class Invoice(TenantMixin, Base):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey('sales_orders.id'), unique=True)
    delivery_note_id = Column(Integer, ForeignKey('delivery_notes.id'), nullable=True)
    # Phase 12: fatura numarasi tenant icinde tekil
    invoice_number = Column(String(50))
    customer_id = Column(Integer, ForeignKey('customers.id'))
    issued_date = Column(Date)
    due_date = Column(Date, nullable=True)
    subtotal = Column(Numeric(18, 4), nullable=True)
    tax_total = Column(Numeric(18, 4), nullable=True)
    total_amount = Column(Numeric(18, 4))
    status = Column(String(20), default='draft')
    # odenmedi|kismi|odendi
    payment_status = Column(String(20), nullable=False, default='odenmedi')
    # Phase 11: belge yasam dongusu (status is durumu icin ayri kalir)
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    delivery_note = relationship('DeliveryNote')
    items = relationship(
        'InvoiceItem', back_populates='invoice', cascade='all, delete-orphan'
    )


class InvoiceItem(TenantMixin, Base):
    __tablename__ = 'invoice_items'
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    delivery_note_item_id = Column(
        Integer, ForeignKey('delivery_note_items.id'), nullable=True
    )
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    tax_rate = Column(Numeric(18, 4), nullable=False, default=0)
    total_price = Column(Numeric(18, 4), nullable=False)

    invoice = relationship('Invoice', back_populates='items')
    product = relationship('Product')
    uom = relationship('UOM')

class User(TenantMixin, Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    # E-posta GLOBAL tekil kalir: giris kimligi, tenant secilmeden once cozulur
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='sales')  # admin | sales
    # Platform sahibi: tum tenant'lari yonetir, tenant filtresinden muaftir
    is_superadmin = Column(Boolean, nullable=False, default=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- Phase 10: Depo ve Stok Defteri ----------------
# Miktar alanlarinda Numeric(18, 4) kullaniliyor; float yuvarlama hatasi
# ERP'de kabul edilemez (bkz. Phase 10 notlari).

WAREHOUSE_TYPES = ('merkez', 'sube', 'arac', 'iade', 'karantina')

STOCK_REASONS = (
    'acilis', 'satis', 'satis_iptal', 'alim', 'alim_iade',
    'transfer_giris', 'transfer_cikis', 'sayim', 'fire', 'duzeltme',
)

STOCK_REF_TYPES = ('sale', 'delivery', 'purchase', 'transfer', 'adjustment', 'opening')


class Warehouse(TenantMixin, Base):
    __tablename__ = 'warehouses'
    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    warehouse_type = Column(String(20), nullable=False, default='merkez')
    parent_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship('Warehouse', remote_side=[id], backref='children')

    __table_args__ = (
        UniqueConstraint('tenant_id', 'code', name='uq_warehouses_tenant_code'),
    )


class StockLedgerEntry(TenantMixin, Base):
    """Degismez stok defteri satiri.

    Bu tablodaki satirlar ASLA UPDATE veya DELETE edilmez. Yanlis giris varsa
    reason='duzeltme' ile ters kayit atilir. Kural stock_service icinde ve
    ORM event'leriyle zorlanir.
    """
    __tablename__ = 'stock_ledger_entries'
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    change_qty = Column(Numeric(18, 4), nullable=False)
    balance_qty = Column(Numeric(18, 4), nullable=False)
    reason = Column(String(20), nullable=False)
    ref_type = Column(String(20), nullable=True)
    ref_id = Column(Integer, nullable=True)
    unit_cost = Column(Numeric(18, 4), nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship('Product')
    warehouse = relationship('Warehouse')

    __table_args__ = (
        # Bakiye sorgulari her zaman (urun, depo) uzerinden zaman sirali gider
        Index('ix_sle_product_warehouse_created', 'product_id', 'warehouse_id', 'created_at'),
        Index('ix_sle_ref', 'ref_type', 'ref_id'),
    )


class StockTransfer(TenantMixin, Base):
    __tablename__ = 'stock_transfers'
    id = Column(Integer, primary_key=True)
    # Phase 12: transfer numarasi tenant icinde tekil
    transfer_no = Column(String(50), nullable=True)
    from_warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    to_warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    transfer_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default='draft')  # draft|completed|cancelled
    # Phase 11: belge yasam dongusu (status is durumu icin ayri kalir)
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    from_warehouse = relationship('Warehouse', foreign_keys=[from_warehouse_id])
    to_warehouse = relationship('Warehouse', foreign_keys=[to_warehouse_id])
    items = relationship(
        'StockTransferItem', back_populates='transfer', cascade='all, delete-orphan'
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'transfer_no', name='uq_transfers_tenant_number'),
    )


class StockTransferItem(TenantMixin, Base):
    __tablename__ = 'stock_transfer_items'
    id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey('stock_transfers.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)

    transfer = relationship('StockTransfer', back_populates='items')
    product = relationship('Product')


# --- Ledger degismezligi: ORM seviyesinde UPDATE/DELETE engeli ---

class LedgerImmutableError(Exception):
    """Stok defteri satiri degistirilmeye/silinmeye calisildiginda firlatilir."""


@event.listens_for(StockLedgerEntry, 'before_update')
def _block_ledger_update(mapper, connection, target):  # noqa: ARG001
    raise LedgerImmutableError(
        'Stok defteri satirlari degistirilemez. Duzeltme icin ters kayit '
        "(reason='duzeltme') atin."
    )


@event.listens_for(StockLedgerEntry, 'before_delete')
def _block_ledger_delete(mapper, connection, target):  # noqa: ARG001
    raise LedgerImmutableError(
        'Stok defteri satirlari silinemez. Duzeltme icin ters kayit '
        "(reason='duzeltme') atin."
    )


# ---------------- Phase 11: Belge durumu, numaralandirma, denetim izi ----------------

class DocStatus:
    """Belge yasam dongusu. `status` (is akisi) ile karistirilmamali."""
    DRAFT = 0
    SUBMITTED = 1
    CANCELLED = 2

    LABELS = {0: 'taslak', 1: 'onayli', 2: 'iptal'}


# docstatus tasiyan modeller - degismezlik kurali bunlara uygulanir
# NOT: `type(obj).__name__` ile karsilastirilir - Sale/SalesItem birer alias
# oldugu icin gercek sinif adlari (SalesOrder) kullanilir.
DOCUMENT_MODELS = (
    'SalesOrder', 'Invoice', 'StockTransfer',
    'PurchaseOrder', 'PurchaseReceipt', 'PurchaseInvoice',
    'Quotation', 'DeliveryNote',
)

# Onayli/iptal belgede degismesine izin verilen alanlar (submit/cancel akisi)
DOC_LIFECYCLE_FIELDS = frozenset({
    'docstatus', 'submitted_at', 'submitted_by',
    'cancelled_at', 'cancelled_by', 'cancel_reason',
    'invoice_number', 'transfer_no', 'status',
    'po_number', 'receipt_number', 'internal_number', 'payment_status',
    'quotation_number', 'so_number', 'delivery_note_number',
})


class NamingSeries(Base):
    """Belge numarasi sayaci. Artis atomik tek SQL ifadesiyle yapilir."""
    __tablename__ = 'naming_series'
    id = Column(Integer, primary_key=True)
    doc_type = Column(String(50), nullable=False)
    prefix = Column(String(20), nullable=False)
    year = Column(Integer, nullable=False)
    current_number = Column(Integer, nullable=False, default=0)
    padding = Column(Integer, nullable=False, default=5)
    # Phase 12'de kullanilacak; simdilik nullable
    tenant_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # PostgreSQL'de NULL'lar birbirinden farkli sayilir; duz bir
    # UNIQUE(doc_type, year, tenant_id) kisiti tenant_id NULL iken MUKERRER
    # satira izin verir. Bu yuzden iki ayri KISMI unique index kullaniliyor.
    __table_args__ = (
        Index(
            'uq_naming_series_global',
            'doc_type', 'year',
            unique=True,
            postgresql_where=text('tenant_id IS NULL'),
        ),
        Index(
            'uq_naming_series_tenant',
            'doc_type', 'year', 'tenant_id',
            unique=True,
            postgresql_where=text('tenant_id IS NOT NULL'),
        ),
    )


class AuditLog(TenantMixin, Base):
    """Kim, ne zaman, hangi alani nasil degistirdi.

    Satirlar degismezdir; yalnizca INSERT edilir.
    """
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    table_name = Column(String(64), nullable=False)
    record_id = Column(Integer, nullable=True)
    action = Column(String(20), nullable=False)  # create|update|delete|submit|cancel
    field_name = Column(String(64), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_audit_table_record', 'table_name', 'record_id'),
        Index('ix_audit_created_at', 'created_at'),
    )


class DocumentImmutableError(Exception):
    """Onaylanmis/iptal edilmis belge degistirilmeye calisildiginda firlatilir."""


# ---------------- Phase 13: Olcu birimi, kategori ve urun yapisi ----------------

# Varsayilan olcu birimleri: (kod, ad, bolunemez mi)
DEFAULT_UOMS = (
    ('adet', 'Adet', True),
    ('kg', 'Kilogram', False),
    ('gram', 'Gram', False),
    ('litre', 'Litre', False),
    ('metre', 'Metre', False),
    ('m2', 'Metrekare', False),
    ('m3', 'Metrekup', False),
    ('paket', 'Paket', True),
    ('koli', 'Koli', True),
    ('kutu', 'Kutu', True),
    ('ton', 'Ton', False),
)

# Urun bagimsiz, evrensel donusumler: (kaynak, hedef, carpan)
DEFAULT_CONVERSIONS = (
    ('kg', 'gram', '1000'),
    ('ton', 'kg', '1000'),
    ('m3', 'litre', '1000'),
)

PRODUCT_TYPES = ('stoklu', 'hizmet', 'sarf')

BARCODE_TYPES = ('EAN13', 'EAN8', 'CODE128', 'QR')


class UOM(TenantMixin, Base):
    """Olcu birimi. `is_integer` bolunemez birimleri isaretler (adet, koli)."""
    __tablename__ = 'uoms'
    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False)
    name = Column(String(50), nullable=False)
    is_integer = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'code', name='uq_uoms_tenant_code'),
    )


class UOMConversion(TenantMixin, Base):
    """Birim donusum carpani.

    `product_id` bossa evrensel donusum (1 kg = 1000 gram),
    doluysa o urune ozel donusum (X urunu icin 1 koli = 12 adet).
    Urune ozel kayit evrensel kaydi EZER.
    """
    __tablename__ = 'uom_conversions'
    id = Column(Integer, primary_key=True)
    from_uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=False)
    to_uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=False)
    # Decimal: "1 top kumas = 47.5 metre" gibi durumlar var
    factor = Column(Numeric(18, 6), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    from_uom = relationship('UOM', foreign_keys=[from_uom_id])
    to_uom = relationship('UOM', foreign_keys=[to_uom_id])

    __table_args__ = (
        UniqueConstraint(
            'tenant_id', 'from_uom_id', 'to_uom_id', 'product_id',
            name='uq_uom_conversion',
        ),
        Index('ix_uom_conversion_lookup', 'tenant_id', 'from_uom_id', 'to_uom_id'),
    )


class ItemGroup(TenantMixin, Base):
    """Urun kategorisi - agac yapi (Elektronik > Bilgisayar > Dizustu)."""
    __tablename__ = 'item_groups'
    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey('item_groups.id'), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship('ItemGroup', remote_side=[id], backref='children')

    __table_args__ = (
        UniqueConstraint('tenant_id', 'code', name='uq_item_groups_tenant_code'),
    )


class Brand(TenantMixin, Base):
    __tablename__ = 'brands'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_brands_tenant_name'),
    )


class ProductBarcode(TenantMixin, Base):
    """Bir urunun birden fazla barkodu olabilir: adet barkodu ayri, koli ayri."""
    __tablename__ = 'product_barcodes'
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, index=True)
    barcode = Column(String(64), nullable=False)
    barcode_type = Column(String(20), nullable=False, default='EAN13')
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship('Product', back_populates='barcodes')
    uom = relationship('UOM')

    __table_args__ = (
        UniqueConstraint('tenant_id', 'barcode', name='uq_barcodes_tenant_code'),
    )


class ItemAttribute(TenantMixin, Base):
    """Varyant ozniteligi: Renk, Beden."""
    __tablename__ = 'item_attributes'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    values = relationship(
        'ItemAttributeValue', back_populates='attribute', cascade='all, delete-orphan',
        order_by='ItemAttributeValue.sort_order',
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_item_attributes_tenant_name'),
    )


class ItemAttributeValue(TenantMixin, Base):
    """Oznitelik degeri: Kirmizi/Mavi, S/M/L."""
    __tablename__ = 'item_attribute_values'
    id = Column(Integer, primary_key=True)
    attribute_id = Column(
        Integer, ForeignKey('item_attributes.id'), nullable=False, index=True
    )
    value = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    attribute = relationship('ItemAttribute', back_populates='values')

    __table_args__ = (
        UniqueConstraint('attribute_id', 'value', name='uq_attribute_value'),
    )


class ProductVariantAttribute(TenantMixin, Base):
    """Varyant urunun hangi oznitelik degerlerine sahip oldugu."""
    __tablename__ = 'product_variant_attributes'
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, index=True)
    attribute_id = Column(Integer, ForeignKey('item_attributes.id'), nullable=False)
    value_id = Column(Integer, ForeignKey('item_attribute_values.id'), nullable=False)

    attribute = relationship('ItemAttribute')
    value = relationship('ItemAttributeValue')

    __table_args__ = (
        UniqueConstraint('product_id', 'attribute_id', name='uq_variant_attribute'),
    )


# ---------------- Phase 14: Tedarikci ve satin alma ----------------

PURCHASE_ORDER_STATUSES = ('beklemede', 'kismi_teslim', 'tamamlandi', 'iptal')

PAYMENT_STATUSES = ('odenmedi', 'kismi', 'odendi')


class Supplier(TenantMixin, Base):
    """Tedarikci karti.

    Musteri ile ayri tablo: Phase 17'de (cari hesap) ortak bir `Party`
    yapisina birlestirilebilir, simdilik erken soyutlama yapilmiyor.
    """
    __tablename__ = 'suppliers'
    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    tax_number = Column(String(11), nullable=True)
    tax_office = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    contact_person = Column(String(255), nullable=True)
    payment_term_days = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'code', name='uq_suppliers_tenant_code'),
    )


class PurchaseOrder(TenantMixin, Base):
    """Satin alma siparisi - NIYET BEYANI, stok hareketi yaratmaz."""
    __tablename__ = 'purchase_orders'
    id = Column(Integer, primary_key=True)
    po_number = Column(String(50), nullable=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, index=True)
    order_date = Column(Date, nullable=False, default=datetime.utcnow)
    expected_date = Column(Date, nullable=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    status = Column(String(20), nullable=False, default='beklemede')
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    subtotal = Column(Numeric(18, 4), nullable=False, default=0)
    tax_total = Column(Numeric(18, 4), nullable=False, default=0)
    grand_total = Column(Numeric(18, 4), nullable=False, default=0)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship('Supplier')
    warehouse = relationship('Warehouse')
    items = relationship(
        'PurchaseOrderItem', back_populates='order',
        cascade='all, delete-orphan', order_by='PurchaseOrderItem.id',
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'po_number', name='uq_po_tenant_number'),
    )


class PurchaseOrderItem(TenantMixin, Base):
    __tablename__ = 'purchase_order_items'
    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(
        Integer, ForeignKey('purchase_orders.id'), nullable=False, index=True
    )
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    received_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    unit_price = Column(Numeric(18, 4), nullable=False)
    tax_rate = Column(Numeric(18, 4), nullable=False, default=0)
    line_total = Column(Numeric(18, 4), nullable=False, default=0)

    order = relationship('PurchaseOrder', back_populates='items')
    product = relationship('Product')
    uom = relationship('UOM')


class PurchaseReceipt(TenantMixin, Base):
    """Mal kabul - STOK HAREKETI YARATAN TEK satin alma belgesi."""
    __tablename__ = 'purchase_receipts'
    id = Column(Integer, primary_key=True)
    receipt_number = Column(String(50), nullable=True)
    purchase_order_id = Column(
        Integer, ForeignKey('purchase_orders.id'), nullable=True, index=True
    )
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    receipt_date = Column(Date, nullable=False, default=datetime.utcnow)
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship('Supplier')
    warehouse = relationship('Warehouse')
    order = relationship('PurchaseOrder')
    items = relationship(
        'PurchaseReceiptItem', back_populates='receipt',
        cascade='all, delete-orphan', order_by='PurchaseReceiptItem.id',
    )

    __table_args__ = (
        UniqueConstraint('tenant_id', 'receipt_number', name='uq_receipt_tenant_number'),
    )


class PurchaseReceiptItem(TenantMixin, Base):
    __tablename__ = 'purchase_receipt_items'
    id = Column(Integer, primary_key=True)
    purchase_receipt_id = Column(
        Integer, ForeignKey('purchase_receipts.id'), nullable=False, index=True
    )
    purchase_order_item_id = Column(
        Integer, ForeignKey('purchase_order_items.id'), nullable=True
    )
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    accepted_quantity = Column(Numeric(18, 4), nullable=False)
    rejected_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    stock_quantity = Column(Numeric(18, 4), nullable=True)
    unit_price = Column(Numeric(18, 4), nullable=False, default=0)
    reject_reason = Column(Text, nullable=True)

    receipt = relationship('PurchaseReceipt', back_populates='items')
    order_item = relationship('PurchaseOrderItem')
    product = relationship('Product')
    uom = relationship('UOM')


class PurchaseInvoice(TenantMixin, Base):
    """Alis faturasi - MALI BELGE, stok hareketi yaratmaz.

    Stok mal kabulde girmistir; fatura yalnizca borcu kaydeder.
    """
    __tablename__ = 'purchase_invoices'
    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), nullable=False)
    internal_number = Column(String(50), nullable=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False, index=True)
    purchase_receipt_id = Column(
        Integer, ForeignKey('purchase_receipts.id'), nullable=True, index=True
    )
    invoice_date = Column(Date, nullable=False, default=datetime.utcnow)
    due_date = Column(Date, nullable=True)
    subtotal = Column(Numeric(18, 4), nullable=False, default=0)
    tax_total = Column(Numeric(18, 4), nullable=False, default=0)
    grand_total = Column(Numeric(18, 4), nullable=False, default=0)
    payment_status = Column(String(20), nullable=False, default='odenmedi')
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship('Supplier')
    receipt = relationship('PurchaseReceipt')
    items = relationship(
        'PurchaseInvoiceItem', back_populates='invoice',
        cascade='all, delete-orphan', order_by='PurchaseInvoiceItem.id',
    )

    __table_args__ = (
        UniqueConstraint(
            'tenant_id', 'supplier_id', 'invoice_number',
            name='uq_pinv_tenant_supplier_number',
        ),
        UniqueConstraint('tenant_id', 'internal_number', name='uq_pinv_tenant_internal'),
    )


class PurchaseInvoiceItem(TenantMixin, Base):
    __tablename__ = 'purchase_invoice_items'
    id = Column(Integer, primary_key=True)
    purchase_invoice_id = Column(
        Integer, ForeignKey('purchase_invoices.id'), nullable=False, index=True
    )
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    tax_rate = Column(Numeric(18, 4), nullable=False, default=0)
    line_total = Column(Numeric(18, 4), nullable=False, default=0)

    invoice = relationship('PurchaseInvoice', back_populates='items')
    product = relationship('Product')
    uom = relationship('UOM')


# Modeller tanimlandiktan SONRA session dinleyicilerini bagla.
# (database.py icinde baglamak dairesel import olusturuyor.)
from .database import register_session_listeners  # noqa: E402

register_session_listeners()