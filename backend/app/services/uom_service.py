"""Olcu birimi donusum servisi (Phase 13).

TEMEL KURAL: stok defterine yazilan miktar HER ZAMAN urunun `stock_uom`
biriminden olur. Alim koli, satis adet olabilir; donusum ledger'a yazmadan
once burada yapilir. Bu kural bozulursa stok hesabi coker.

Carpanlar `Decimal` (Numeric(18, 6)): "1 top kumas = 47.5 metre" gibi
ondalikli donusumler gercek.
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import UOM, Product, UOMConversion

ONE = Decimal('1')


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def get_uom(db: Session, uom_id: Optional[int]) -> Optional[UOM]:
    if uom_id is None:
        return None
    uom = db.get(UOM, uom_id)
    if uom is None:
        raise HTTPException(status_code=404, detail=f'Olcu birimi {uom_id} bulunamadi')
    return uom


def find_factor(
    db: Session, from_uom_id: int, to_uom_id: int, product_id: Optional[int] = None
) -> Optional[Decimal]:
    """Donusum carpanini bulur.

    Oncelik sirasi:
      1. Urune ozel kayit (product_id dolu) - genel kaydi EZER
      2. Evrensel kayit (product_id NULL)
      3. Ters yonde kayit varsa 1/carpan
    """
    if from_uom_id == to_uom_id:
        return ONE

    def lookup(source: int, target: int):
        rows = (
            db.query(UOMConversion)
            .filter(
                UOMConversion.from_uom_id == source,
                UOMConversion.to_uom_id == target,
                or_(
                    UOMConversion.product_id == product_id,
                    UOMConversion.product_id.is_(None),
                ),
            )
            .all()
        )
        if not rows:
            return None
        # Urune ozel kayit varsa once o gelsin
        rows.sort(key=lambda r: 0 if r.product_id is not None else 1)
        return to_decimal(rows[0].factor)

    direct = lookup(from_uom_id, to_uom_id)
    if direct is not None:
        return direct

    reverse = lookup(to_uom_id, from_uom_id)
    if reverse is not None and reverse != 0:
        return ONE / reverse
    return None


def convert(
    db: Session,
    quantity,
    from_uom_id: Optional[int],
    to_uom_id: Optional[int],
    product_id: Optional[int] = None,
) -> Decimal:
    """Miktari bir birimden digerine cevirir.

    Birimlerden biri tanimsizsa (eski kayitlar) donusum yapilmaz - miktar
    oldugu gibi doner. Boylece Phase 13 oncesi veri kirilmaz.
    """
    qty = to_decimal(quantity)
    if from_uom_id is None or to_uom_id is None or from_uom_id == to_uom_id:
        return qty

    factor = find_factor(db, from_uom_id, to_uom_id, product_id)
    if factor is None:
        from_uom = get_uom(db, from_uom_id)
        to_uom = get_uom(db, to_uom_id)
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{from_uom.code}" -> "{to_uom.code}" icin donusum tanimli degil. '
                'Once birim donusumu ekleyin.'
            ),
        )
    return qty * factor


def to_stock_uom(db: Session, product: Product, quantity, from_uom_id: Optional[int]):
    """Miktari urunun stok birimine cevirir. Ledger'a yazmadan once cagrilir."""
    if from_uom_id is None or product.stock_uom_id is None:
        return to_decimal(quantity)
    return convert(db, quantity, from_uom_id, product.stock_uom_id, product.id)


def ensure_defaults(db: Session, tenant_id: Optional[int]) -> dict:
    """Tenant icin varsayilan birimleri ve evrensel donusumleri olusturur.

    Idempotent: var olan birim tekrar eklenmez.
    """
    from ..models import DEFAULT_CONVERSIONS, DEFAULT_UOMS

    existing = {
        u.code: u
        for u in db.query(UOM).filter(UOM.tenant_id == tenant_id).all()
    }
    for code, name, is_integer in DEFAULT_UOMS:
        if code in existing:
            continue
        uom = UOM(
            tenant_id=tenant_id, code=code, name=name,
            is_integer=is_integer, is_active=True,
        )
        db.add(uom)
        existing[code] = uom
    db.flush()

    for from_code, to_code, factor in DEFAULT_CONVERSIONS:
        source, target = existing.get(from_code), existing.get(to_code)
        if source is None or target is None:
            continue
        already = (
            db.query(UOMConversion)
            .filter(
                UOMConversion.tenant_id == tenant_id,
                UOMConversion.from_uom_id == source.id,
                UOMConversion.to_uom_id == target.id,
                UOMConversion.product_id.is_(None),
            )
            .first()
        )
        if already is None:
            db.add(
                UOMConversion(
                    tenant_id=tenant_id,
                    from_uom_id=source.id,
                    to_uom_id=target.id,
                    factor=to_decimal(factor),
                    product_id=None,
                )
            )
    db.flush()
    return existing
