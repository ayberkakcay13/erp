"""Belge yasam dongusu servisi (Phase 11, Phase 15'te satis zinciri icin genisletildi).

`submit()` ve `cancel()` belgelerin tek gecis noktasidir. Yan etkiler
(stok hareketi, numara atama) burada tetiklenir - router'lar dogrudan
`stock_service` cagirmaz.

Kurallar:
- taslak (0) -> onayli (1): numara atanir, stok hareketi yazilir
- onayli (1) -> iptal (2): ters stok hareketi yazilir
- iptal edilen belge TEKRAR ONAYLANAMAZ. Duzeltme icin yeni belge kesilir.
  (Bu kural Phase 4/10'daki "iptali geri al" davranisinin yerini alir.)

Phase 15 satis zinciri: Quotation -> SalesOrder -> DeliveryNote -> Invoice.
STOK HAREKETI YALNIZCA DeliveryNote onayinda olusur (reason='satis',
ref_type='delivery'). SalesOrder onayi niyet beyanidir, stok hareketi
yaratmaz - eski `Sale` davranisinin (onay = stok dususu) yerini bu alir.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    Customer,
    DeliveryNote,
    DocStatus,
    Invoice,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseReceipt,
    Quotation,
    SalesOrder,
    SalesOrderItem,
    StockTransfer,
)
from . import (
    audit_service,
    naming_service,
    purchase_service,
    stock_service,
    tenant_context,
    uom_service,
)

# Belge tipi -> (numaralandirma doc_type, numara alani)
NUMBERING = {
    Quotation: ('quotation', 'quotation_number'),
    SalesOrder: ('sales_order', 'so_number'),
    DeliveryNote: ('delivery_note', 'delivery_note_number'),
    Invoice: ('invoice', 'invoice_number'),
    StockTransfer: ('transfer', 'transfer_no'),
    PurchaseOrder: ('purchase_order', 'po_number'),
    PurchaseReceipt: ('purchase_receipt', 'receipt_number'),
    PurchaseInvoice: ('purchase_invoice', 'internal_number'),
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

def _delivery_stock_entries(
    db: Session, delivery_note: DeliveryNote, submitting: bool, user_id, note: str
) -> None:
    """Sevkiyat kalemlerini (urun, depo) kiriliminda ledger'a isler.

    Phase 15: stok hareketi YALNIZCA burada olusur. Phase 13 kurali gecerli -
    ledger'a yazilan miktar her zaman urunun stok biriminde olur; kalem
    olusturulurken `stock_quantity` alanina onceden yazilmistir.

    Ayrica bagli SalesOrderItem.delivered_quantity guncellenir - kismi
    sevkiyat hesabinin temeli budur. `SalesOrder.status` burada DEGISTIRILMEZ;
    `/api/sales` uyum katmani kendi status degerini korur, yeni akis
    `sales_order_service.refresh_delivery_status()` cagirir.
    """
    totals: dict[tuple[int, int], object] = {}
    for item in delivery_note.items:
        wh_id = stock_service.resolve_warehouse_id(
            db, item.warehouse_id or delivery_note.warehouse_id
        )
        quantity = item.stock_quantity
        if quantity is None:
            quantity = item.quantity
        key = (item.product_id, wh_id)
        totals[key] = totals.get(key, stock_service.ZERO) + stock_service.to_decimal(quantity)

    reason = 'satis' if submitting else 'satis_iptal'
    sign = -1 if submitting else 1
    for (product_id, wh_id), quantity in totals.items():
        stock_service.add_entry(
            db,
            product_id=product_id,
            warehouse_id=wh_id,
            change_qty=sign * quantity,
            reason=reason,
            ref_type='delivery',
            ref_id=delivery_note.id,
            user_id=user_id,
            note=note,
        )

    delta_sign = 1 if submitting else -1
    for item in delivery_note.items:
        if item.sales_order_item_id is None:
            continue
        order_item = db.get(SalesOrderItem, item.sales_order_item_id)
        if order_item is None:
            continue
        quantity = item.stock_quantity if item.stock_quantity is not None else item.quantity
        quantity = stock_service.to_decimal(quantity)
        if item.uom_id and order_item.uom_id and item.uom_id != order_item.uom_id:
            quantity = uom_service.convert(
                db, quantity, item.uom_id, order_item.uom_id, order_item.product_id
            )
        order_item.delivered_quantity = (
            stock_service.to_decimal(order_item.delivered_quantity)
            + delta_sign * quantity
        )


def _transfer_stock_entries(db: Session, transfer: StockTransfer, sign: int, user_id, note):
    # Transfer kalemleri zaten stok biriminde girilir
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


def _purchase_invoice_effects(db: Session, invoice: PurchaseInvoice) -> None:
    """Alis faturasi stok hareketi yaratmaz; yalnizca vadeyi tamamlar."""
    if invoice.due_date is None:
        supplier = purchase_service.get_supplier(db, invoice.supplier_id)
        invoice.due_date = purchase_service.due_date_for(supplier, invoice.invoice_date)


def _sales_invoice_effects(db: Session, invoice: Invoice) -> None:
    """Satis faturasi stok hareketi yaratmaz (stok sevkiyatta gitmistir).

    `due_date` bossa musterinin vade gun sayisindan (Customer.credit_days)
    hesaplanir.
    """
    if invoice.due_date is not None or invoice.issued_date is None:
        return
    customer = db.get(Customer, invoice.customer_id) if invoice.customer_id else None
    days = customer.credit_days if customer else 0
    invoice.due_date = invoice.issued_date + timedelta(days=days or 0)


def _apply_effects(db: Session, doc, submitting: bool, user_id, note: str) -> None:
    if isinstance(doc, DeliveryNote):
        _delivery_stock_entries(db, doc, submitting, user_id, note)
    elif isinstance(doc, StockTransfer):
        _transfer_stock_entries(db, doc, 1 if submitting else -1, user_id, note)
    elif isinstance(doc, PurchaseReceipt):
        purchase_service.apply_receipt(db, doc, 1 if submitting else -1, user_id)
    elif isinstance(doc, PurchaseInvoice) and submitting:
        _purchase_invoice_effects(db, doc)
    elif isinstance(doc, Invoice) and submitting:
        _sales_invoice_effects(db, doc)
    # SalesOrder ve Quotation'in stok yan etkisi yok - stok yalnizca
    # DeliveryNote onayinda hareket eder (Phase 15 kurali).


# ---------------- Genel gecisler ----------------

def submit(db: Session, doc, user_id: Optional[int] = None):
    """Taslak belgeyi onaylar: numara atar ve yan etkileri tetikler.

    commit ETMEZ - cagiran router kendi transaction'inda commit eder.
    """
    _require_draft(doc)

    doc_type, number_field = NUMBERING.get(type(doc), (None, None))
    if doc_type and number_field and not getattr(doc, number_field, None):
        # Numara ONAY aninda atanir; silinen taslaklar bosluk birakmasin
        # Numara serisi tenant bazli: her firmanin kendi FT-2026-00001 dizisi olur
        setattr(
            doc,
            number_field,
            naming_service.get_next_number(
                db, doc_type, tenant_id=tenant_context.current_tenant_id.get()
            ),
        )

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
