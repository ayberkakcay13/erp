from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, text,
)
from sqlalchemy import event
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class Customer(Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    sales = relationship('Sale', back_populates='customer', cascade='all, delete-orphan')

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    sku = Column(String(50), unique=True, nullable=False)
    price = Column(Numeric(18, 4), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    sales_items = relationship('SalesItem', back_populates='product')

class Sale(Base):
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

class SalesItem(Base):
    __tablename__ = 'sales_items'
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey('sales.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    total_price = Column(Numeric(18, 4), nullable=False)
    # Phase 10: satis kalemi hangi depodan cikti (bossa varsayilan depo)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    sale = relationship('Sale', back_populates='items')
    product = relationship('Product', back_populates='sales_items')

class Invoice(Base):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey('sales.id'), unique=True)
    invoice_number = Column(String(50), unique=True)
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

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='sales')  # admin | sales
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


class Warehouse(Base):
    __tablename__ = 'warehouses'
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    warehouse_type = Column(String(20), nullable=False, default='merkez')
    parent_id = Column(Integer, ForeignKey('warehouses.id'), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship('Warehouse', remote_side=[id], backref='children')


class StockLedgerEntry(Base):
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


class StockTransfer(Base):
    __tablename__ = 'stock_transfers'
    id = Column(Integer, primary_key=True)
    transfer_no = Column(String(50), unique=True, nullable=False)
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


class StockTransferItem(Base):
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


class AuditLog(Base):
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
