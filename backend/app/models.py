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
DEFAULT_ENABLED_MODULES = ('sales', 'stock', 'invoice', 'reports')

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
    sales = relationship('Sale', back_populates='customer', cascade='all, delete-orphan')

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

    sales_items = relationship('SalesItem', back_populates='product')
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

class Sale(TenantMixin, Base):
    __tablename__ = 'sales'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    sale_date = Column(Date, nullable=False)
    total_amount = Column(Numeric(18, 4), nullable=False)
    status = Column(String(20), default='pending')
    # Phase 11: belge yasam dongusu (status is durumu icin ayri kalir)
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    customer = relationship('Customer', back_populates='sales')
    items = relationship('SalesItem', back_populates='sale', cascade='all, delete-orphan')

class SalesItem(TenantMixin, Base):
    __tablename__ = 'sales_items'
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey('sales.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    total_price = Column(Numeric(18, 4), nullable=False)
    # Phase 10: satis kalemi hangi depodan cikti (bossa varsayilan depo)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    # Phase 13: `quantity` musterinin girdigi birimde (fiyat da o birimde),
    # `stock_quantity` ise stok birimine cevrilmis hali - ledger bunu kullanir.
    uom_id = Column(Integer, ForeignKey('uoms.id'), nullable=True)
    stock_quantity = Column(Numeric(18, 4), nullable=True)
    sale = relationship('Sale', back_populates='items')
    product = relationship('Product', back_populates='sales_items')
    uom = relationship('UOM')

class Invoice(TenantMixin, Base):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey('sales.id'), unique=True)
    # Phase 12: fatura numarasi tenant icinde tekil
    invoice_number = Column(String(50))
    customer_id = Column(Integer, ForeignKey('customers.id'))
    issued_date = Column(Date)
    total_amount = Column(Numeric(18, 4))
    status = Column(String(20), default='draft')
    # Phase 11: belge yasam dongusu (status is durumu icin ayri kalir)
    docstatus = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

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

STOCK_REF_TYPES = ('sale', 'purchase', 'transfer', 'adjustment', 'opening')


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
DOCUMENT_MODELS = ('Sale', 'Invoice', 'StockTransfer')

# Onayli/iptal belgede degismesine izin verilen alanlar (submit/cancel akisi)
DOC_LIFECYCLE_FIELDS = frozenset({
    'docstatus', 'submitted_at', 'submitted_by',
    'cancelled_at', 'cancelled_by', 'cancel_reason',
    'invoice_number', 'transfer_no', 'status',
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


# Modeller tanimlandiktan SONRA session dinleyicilerini bagla.
# (database.py icinde baglamak dairesel import olusturuyor.)
from .database import register_session_listeners  # noqa: E402

register_session_listeners()