"""Stok defteri servisi (Phase 10).

Stoga dair TEK giris noktasi burasi. Hicbir router dogrudan
`stock_ledger_entries` tablosuna INSERT atmaz; hepsi `add_entry()` cagirir.

Tasarim kurallari:
- Miktarlar `Decimal` (kolonlar `Numeric(18, 4)`). Float kullanilmaz.
- Ledger degismezdir: satir UPDATE/DELETE edilmez, ters kayit atilir.
- Ayni urun icin es zamanli hareketler `SELECT ... FOR UPDATE` ile serilestirilir.
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    STOCK_REASONS,
    STOCK_REF_TYPES,
    Product,
    StockLedgerEntry,
    Warehouse,
)

# Negatif stok varsayilan olarak yasak. Ayar ile acilabilir
# (ornegin konsinye / asamali mal kabul senaryolari icin).
ALLOW_NEGATIVE_STOCK = False

ZERO = Decimal('0')


def to_decimal(value) -> Decimal:
    """Girdiyi float'a ugramadan Decimal'e cevirir."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# ---------------- Depo yardimcilari ----------------

def get_default_warehouse(db: Session) -> Warehouse:
    """Varsayilan depoyu getirir; hic depo yoksa 400 doner."""
    wh = db.query(Warehouse).filter(Warehouse.is_default.is_(True)).first()
    if wh is None:
        wh = (
            db.query(Warehouse)
            .filter(Warehouse.is_active.is_(True))
            .order_by(Warehouse.id)
            .first()
        )
    if wh is None:
        raise HTTPException(
            status_code=400,
            detail='Tanimli depo yok. Once bir depo olusturun (varsayilan: Merkez Depo).',
        )
    return wh


def resolve_warehouse_id(db: Session, warehouse_id: Optional[int]) -> int:
    """warehouse_id bossa varsayilan depoyu, doluysa dogrulanmis id'yi doner."""
    if warehouse_id is None:
        return get_default_warehouse(db).id
    wh = db.get(Warehouse, warehouse_id)
    if wh is None:
        raise HTTPException(status_code=404, detail=f'Warehouse {warehouse_id} bulunamadi')
    if not wh.is_active:
        raise HTTPException(status_code=400, detail=f'"{wh.name}" deposu pasif durumda')
    return wh.id


# ---------------- Bakiye okuma ----------------

def get_stock(db: Session, product_id: int, warehouse_id: Optional[int] = None) -> Decimal:
    """Ledger toplamindan guncel stok. warehouse_id yoksa tum depolarin toplami."""
    query = select(func.coalesce(func.sum(StockLedgerEntry.change_qty), 0)).where(
        StockLedgerEntry.product_id == product_id
    )
    if warehouse_id is not None:
        query = query.where(StockLedgerEntry.warehouse_id == warehouse_id)
    return to_decimal(db.execute(query).scalar() or 0)


def get_stock_map(db: Session, product_ids=None, warehouse_id: Optional[int] = None) -> dict:
    """Coklu urun icin tek sorguda {product_id: Decimal} bakiye haritasi.

    Urun listesi sayfalarinda N+1 sorgudan kacinmak icin var.
    """
    query = select(
        StockLedgerEntry.product_id,
        func.coalesce(func.sum(StockLedgerEntry.change_qty), 0),
    ).group_by(StockLedgerEntry.product_id)
    if product_ids is not None:
        ids = list(product_ids)
        if not ids:
            return {}
        query = query.where(StockLedgerEntry.product_id.in_(ids))
    if warehouse_id is not None:
        query = query.where(StockLedgerEntry.warehouse_id == warehouse_id)
    return {row[0]: to_decimal(row[1] or 0) for row in db.execute(query).all()}


def check_availability(db: Session, product_id: int, warehouse_id: Optional[int], qty) -> bool:
    """Istenen miktar kadar stok var mi."""
    return get_stock(db, product_id, warehouse_id) >= to_decimal(qty)


# ---------------- Yazma (tek giris noktasi) ----------------

def _lock_product(db: Session, product_id: int) -> Product:
    """Urun satirini kilitler.

    Ayni urunun stogunu es zamanli degistiren iki transaction burada
    serilesir; ikincisi birincinin commit'ini bekler ve guncel bakiyeyi gorur.
    """
    product = db.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail=f'Product {product_id} bulunamadi')
    return product


def add_entry(
    db: Session,
    product_id: int,
    warehouse_id: Optional[int],
    change_qty,
    reason: str,
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
    user_id: Optional[int] = None,
    note: Optional[str] = None,
    allow_negative: Optional[bool] = None,
    unit_cost=None,
) -> StockLedgerEntry:
    """Ledger'a tek bir hareket yazar ve bakiyeyi otomatik hesaplar.

    commit ETMEZ - cagiran router kendi transaction'inda commit eder; boylece
    belge kaydi ile stok hareketi ya birlikte yazilir ya da hic yazilmaz.
    """
    if reason not in STOCK_REASONS:
        raise HTTPException(status_code=400, detail=f'Gecersiz stok nedeni: {reason}')
    if ref_type is not None and ref_type not in STOCK_REF_TYPES:
        raise HTTPException(status_code=400, detail=f'Gecersiz ref_type: {ref_type}')

    change = to_decimal(change_qty)
    if change == ZERO:
        raise HTTPException(status_code=400, detail='change_qty sifir olamaz')

    wh_id = resolve_warehouse_id(db, warehouse_id)
    product = _lock_product(db, product_id)  # bakiye okumasi ile yazma arasinda yaris olmasin

    # Phase 13: sablon urun ve hizmet urunu stok tutmaz
    from . import product_service

    product_service.ensure_not_template(product)

    current = get_stock(db, product_id, wh_id)
    new_balance = current + change

    negative_ok = ALLOW_NEGATIVE_STOCK if allow_negative is None else allow_negative
    if new_balance < ZERO and not negative_ok:
        product = db.get(Product, product_id)
        name = product.name if product else f'Product {product_id}'
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{name}" icin stok yetersiz: {abs(change)} adet istendi, '
                f'depoda {current} adet var'
            ),
        )

    entry = StockLedgerEntry(
        product_id=product_id,
        warehouse_id=wh_id,
        change_qty=change,
        balance_qty=new_balance,
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
        unit_cost=None if unit_cost is None else to_decimal(unit_cost),
        created_by=user_id,
    )
    db.add(entry)
    # id ve bakiye hemen gorunsun; ayni transaction icinde arka arkaya hareket olabilir
    db.flush()
    return entry


def entries_for_ref(db: Session, ref_type: str, ref_id: int, reason: Optional[str] = None):
    """Bir belgeye ait ledger satirlarini doner."""
    query = db.query(StockLedgerEntry).filter(
        StockLedgerEntry.ref_type == ref_type,
        StockLedgerEntry.ref_id == ref_id,
    )
    if reason is not None:
        query = query.filter(StockLedgerEntry.reason == reason)
    return query.order_by(StockLedgerEntry.id).all()
