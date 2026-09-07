"""Belge yasam dongusu servisi (Phase 11).

`submit()` ve `cancel()` belgelerin tek gecis noktasidir. Yan etkiler
(stok hareketi, numara atama) burada tetiklenir - router'lar dogrudan
`stock_service` cagirmaz.

Kurallar:
- taslak (0) -> onayli (1): numara atanir, stok hareketi yazilir
- onayli (1) -> iptal (2): ters stok hareketi yazilir
- iptal edilen belge TEKRAR ONAYLANAMAZ. Duzeltme icin yeni belge kesilir.
  (Bu kural Phase 4/10'daki "iptali geri al" davranisinin yerini alir.)
"""
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import DocStatus, Invoice, Sale, StockTransfer
from . import audit_service, naming_service, stock_service

# Belge tipi -> (numaralandirma doc_type, numara alani)
NUMBERING = {
    Sale: (None, None),                     # satis numarasi zorunlu degil
    Invoice: ('invoice', 'invoice_number'),
    StockTransfer: ('transfer', 'transfer_no'),
}


def label(docstatus: int) -> str:
    return DocStatus.LABELS.get(docstatus, str(docstatus))


def _require_draft(doc) -> None:
    if doc.docstatus == DocStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail='Belge zaten onayli')
    if doc.docstatus == DocStatus.CANCELLED:
        raise HTTPException(
            status_code=400,
            detail=(
                'Iptal edilmis belge tekrar onaylanamaz. '
                'Duzeltme icin yeni bir belge olusturun.'
            ),
        )


def _require_submitted(doc) -> None:
    if doc.docstatus == DocStatus.DRAFT:
        raise HTTPException(
            status_code=400, detail='Taslak belge iptal edilemez, silinebilir'
        )
    if doc.docstatus == DocStatus.CANCELLED:
        raise HTTPException(status_code=400, detail='Belge zaten iptal edilmis')


# ---------------- Yan etkiler ----------------

def _sale_stock_entries(db: Session, sale: Sale, sign: int, user_id, note: str) -> None:
    """Satis kalemlerini (urun, depo) kiriliminda ledger'a isler."""
    totals: dict[tuple[int, int], object] = {}
    for item in sale.items:
        wh_id = stock_service.resolve_warehouse_id(db, item.warehouse_id)
        key = (item.product_id, wh_id)
        totals[key] = totals.get(key, stock_service.ZERO) + stock_service.to_decimal(
            item.quantity
        )

    reason = 'satis' if sign < 0 else 'satis_iptal'
    for (product_id, wh_id), quantity in totals.items():
        stock_service.add_entry(
            db,
            product_id=product_id,
            warehouse_id=wh_id,
            change_qty=sign * quantity,
            reason=reason,
            ref_type='sale',
            ref_id=sale.id,
            user_id=user_id,
            note=note,
        )


def _transfer_stock_entries(db: Session, transfer: StockTransfer, sign: int, user_id, note):
    totals: dict[int, object] = {}
    for item in transfer.items:
        totals[item.product_id] = totals.get(
            item.product_id, stock_service.ZERO
        ) + stock_service.to_decimal(item.quantity)

    # Onayda: cikis deposundan dus, giris deposuna ekle. Iptalde tersi.
    for product_id, quantity in totals.items():
        stock_service.add_entry(
            db, product_id, transfer.from_warehouse_id, -sign * quantity,
            'transfer_cikis' if sign > 0 else 'transfer_giris',
            ref_type='transfer', ref_id=transfer.id, user_id=user_id, note=note,
        )
        stock_service.add_entry(
            db, product_id, transfer.to_warehouse_id, sign * quantity,
            'transfer_giris' if sign > 0 else 'transfer_cikis',
            ref_type='transfer', ref_id=transfer.id, user_id=user_id, note=note,
        )


def _apply_effects(db: Session, doc, submitting: bool, user_id, note: str) -> None:
    if isinstance(doc, Sale):
        _sale_stock_entries(db, doc, -1 if submitting else 1, user_id, note)
    elif isinstance(doc, StockTransfer):
        _transfer_stock_entries(db, doc, 1 if submitting else -1, user_id, note)
    # Invoice'in stok yan etkisi yok - stok satista hareket eder.


# ---------------- Genel gecisler ----------------

def submit(db: Session, doc, user_id: Optional[int] = None):
    """Taslak belgeyi onaylar: numara atar ve yan etkileri tetikler.

    commit ETMEZ - cagiran router commit eder.
    """
    _require_draft(doc)

    doc_type, number_field = NUMBERING.get(type(doc), (None, None))
    if doc_type and number_field and not getattr(doc, number_field, None):
        # Numara ONAY aninda atanir; silinen taslaklar bosluk birakmasin
        setattr(doc, number_field, naming_service.get_next_number(db, doc_type))

    _apply_effects(db, doc, submitting=True, user_id=user_id, note='Belge onaylandi')

    with audit_service.lifecycle_write():
        doc.docstatus = DocStatus.SUBMITTED
        doc.submitted_at = datetime.utcnow()
        doc.submitted_by = user_id
        db.flush()
    return doc


def cancel(db: Session, doc, user_id: Optional[int] = None, reason: Optional[str] = None):
    """Onayli belgeyi iptal eder ve yan etkileri geri alir."""
    _require_submitted(doc)

    _apply_effects(db, doc, submitting=False, user_id=user_id, note='Belge iptal edildi')

    with audit_service.lifecycle_write():
        doc.docstatus = DocStatus.CANCELLED
        doc.cancelled_at = datetime.utcnow()
        doc.cancelled_by = user_id
        doc.cancel_reason = reason
        db.flush()
    return doc


def ensure_editable(doc) -> None:
    """Router'larda is alani guncellemeden once cagrilir; erken ve net hata verir."""
    if doc.docstatus != DocStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=(
                f'{label(doc.docstatus).capitalize()} belge degistirilemez. '
                'Yalnizca taslak belgeler duzenlenebilir.'
            ),
        )


def ensure_deletable(doc) -> None:
    if doc.docstatus != DocStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=(
                f'{label(doc.docstatus).capitalize()} belge silinemez. '
                'Yalnizca taslak belgeler silinebilir.'
            ),
        )
