"""Alis faturasi endpointleri (Phase 14).

Fatura mali belgedir: stok hareketi yaratmaz, stok mal kabulde girmistir.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    PAYMENT_STATUSES,
    DocStatus,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseReceipt,
    User,
)
from ..schemas import (
    CancelRequest,
    PurchaseInvoiceCreate,
    PurchaseInvoiceResponse,
    PurchaseInvoiceUpdate,
)
from ..services import document_service, purchase_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/purchase-invoices',
    tags=['purchase-invoices'],
    dependencies=[Depends(get_current_user), Depends(require_module('purchase'))],
)

DUPLICATE_DETAIL = (
    'Bu tedarikciden bu fatura numarasi zaten girilmis. '
    'Ayni fatura iki kez kaydedilemez.'
)


def _load(db: Session, invoice_id: int) -> PurchaseInvoice:
    invoice = (
        db.query(PurchaseInvoice)
        .options(
            joinedload(PurchaseInvoice.supplier),
            joinedload(PurchaseInvoice.receipt),
            joinedload(PurchaseInvoice.items).joinedload(PurchaseInvoiceItem.product),
            joinedload(PurchaseInvoice.items).joinedload(PurchaseInvoiceItem.uom),
        )
        .filter(PurchaseInvoice.id == invoice_id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail=f'Alis faturasi {invoice_id} bulunamadi')
    return invoice


def _serialize(invoice: PurchaseInvoice) -> dict:
    return {
        'id': invoice.id,
        'invoice_number': invoice.invoice_number,
        'internal_number': invoice.internal_number,
        'supplier_id': invoice.supplier_id,
        'supplier_name': invoice.supplier.name if invoice.supplier else None,
        'purchase_receipt_id': invoice.purchase_receipt_id,
        'receipt_number': invoice.receipt.receipt_number if invoice.receipt else None,
        'invoice_date': invoice.invoice_date,
        'due_date': invoice.due_date,
        'subtotal': invoice.subtotal,
        'tax_total': invoice.tax_total,
        'grand_total': invoice.grand_total,
        'payment_status': invoice.payment_status,
        'docstatus': invoice.docstatus,
        'docstatus_label': DocStatus.LABELS.get(invoice.docstatus),
        'submitted_at': invoice.submitted_at,
        'cancelled_at': invoice.cancelled_at,
        'cancel_reason': invoice.cancel_reason,
        'note': invoice.note,
        'created_at': invoice.created_at,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
                'uom_id': item.uom_id,
                'uom_code': item.uom.code if item.uom else None,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'tax_rate': item.tax_rate,
                'line_total': item.line_total,
            }
            for item in invoice.items
        ],
    }


def _build_items(db: Session, invoice: PurchaseInvoice, items) -> None:
    invoice.items.clear()
    for entry in items:
        product = purchase_service.get_product(db, entry.product_id)
        invoice.items.append(
            PurchaseInvoiceItem(
                product_id=product.id,
                uom_id=entry.uom_id or product.purchase_uom_id or product.stock_uom_id,
                quantity=entry.quantity,
                unit_price=entry.unit_price,
                tax_rate=entry.tax_rate,
            )
        )
    purchase_service.recalc_totals(invoice)


@router.post(
    '', response_model=PurchaseInvoiceResponse, status_code=status.HTTP_201_CREATED
)
def create_invoice(
    payload: PurchaseInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supplier = purchase_service.get_supplier(db, payload.supplier_id)
    if payload.purchase_receipt_id is not None:
        receipt = db.get(PurchaseReceipt, payload.purchase_receipt_id)
        if receipt is None:
            raise HTTPException(
                status_code=404,
                detail=f'Mal kabul {payload.purchase_receipt_id} bulunamadi',
            )

    invoice_date = payload.invoice_date or date.today()
    invoice = PurchaseInvoice(
        invoice_number=payload.invoice_number,
        supplier_id=payload.supplier_id,
        purchase_receipt_id=payload.purchase_receipt_id,
        invoice_date=invoice_date,
        due_date=payload.due_date or purchase_service.due_date_for(supplier, invoice_date),
        payment_status='odenmedi',
        note=payload.note,
        created_by=current_user.id,
    )
    _build_items(db, invoice, payload.items)
    db.add(invoice)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_DETAIL)

    if not payload.save_as_draft:
        document_service.submit(db, invoice, user_id=current_user.id)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_DETAIL)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura kaydedilemedi: {exc}')
    return _serialize(_load(db, invoice.id))


@router.get('', response_model=list[PurchaseInvoiceResponse])
def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    supplier_id: int | None = Query(None),
    payment_status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(PurchaseInvoice).options(
        joinedload(PurchaseInvoice.supplier),
        joinedload(PurchaseInvoice.receipt),
        joinedload(PurchaseInvoice.items).joinedload(PurchaseInvoiceItem.product),
        joinedload(PurchaseInvoice.items).joinedload(PurchaseInvoiceItem.uom),
    )
    if supplier_id is not None:
        query = query.filter(PurchaseInvoice.supplier_id == supplier_id)
    if payment_status is not None:
        query = query.filter(PurchaseInvoice.payment_status == payment_status)
    invoices = query.order_by(PurchaseInvoice.id.desc()).offset(skip).limit(limit).all()
    return [_serialize(invoice) for invoice in invoices]


@router.get('/{invoice_id}', response_model=PurchaseInvoiceResponse)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return _serialize(_load(db, invoice_id))


@router.put('/{invoice_id}', response_model=PurchaseInvoiceResponse)
def update_invoice(
    invoice_id: int, payload: PurchaseInvoiceUpdate, db: Session = Depends(get_db)
):
    invoice = _load(db, invoice_id)
    data = payload.model_dump(exclude_unset=True)
    items = data.pop('items', None)
    payment_status = data.pop('payment_status', None)

    if data or items is not None:
        document_service.ensure_editable(invoice)
    for field, value in data.items():
        setattr(invoice, field, value)
    if items is not None:
        _build_items(db, invoice, payload.items)

    if payment_status is not None:
        if payment_status not in PAYMENT_STATUSES:
            raise HTTPException(
                status_code=400, detail=f'Gecersiz odeme durumu: {payment_status}'
            )
        invoice.payment_status = payment_status

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_DETAIL)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura guncellenemedi: {exc}')
    return _serialize(_load(db, invoice_id))


@router.post('/{invoice_id}/submit', response_model=PurchaseInvoiceResponse)
def submit_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = _load(db, invoice_id)
    document_service.submit(db, invoice, user_id=current_user.id)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura onaylanamadi: {exc}')
    return _serialize(_load(db, invoice_id))


@router.post('/{invoice_id}/cancel', response_model=PurchaseInvoiceResponse)
def cancel_invoice(
    invoice_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = _load(db, invoice_id)
    reason = payload.reason if payload else None
    document_service.cancel(db, invoice, user_id=current_user.id, reason=reason)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura iptal edilemedi: {exc}')
    return _serialize(_load(db, invoice_id))


@router.delete('/{invoice_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = _load(db, invoice_id)
    document_service.ensure_deletable(invoice)
    try:
        db.delete(invoice)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura silinemedi: {exc}')
    return None
