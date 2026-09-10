"""Teklif (Quotation) endpointleri (Phase 15).

Teklif opsiyoneldir - satis siparisi dogrudan da acilabilir. Teklifin
stok/kredi yan etkisi yoktur; yalnizca musteriye "teklif gonderildi" kaydi
tutar ve kabul edilirse kalemleriyle birlikte bir SalesOrder'a donusur.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import Customer, DocStatus, Quotation, QuotationItem, SalesOrder, SalesOrderItem, User
from ..schemas import (
    CancelRequest,
    QuotationCreate,
    QuotationResponse,
    QuotationToSalesOrderRequest,
    QuotationUpdate,
)
from ..services import document_service, sales_order_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/quotations',
    tags=['quotations'],
    dependencies=[Depends(get_current_user), Depends(require_module('sales'))],
)


def _load(db: Session, quotation_id: int) -> Quotation:
    quotation = (
        db.query(Quotation)
        .options(
            joinedload(Quotation.customer),
            joinedload(Quotation.items).joinedload(QuotationItem.product),
            joinedload(Quotation.items).joinedload(QuotationItem.uom),
        )
        .filter(Quotation.id == quotation_id)
        .first()
    )
    if quotation is None:
        raise HTTPException(status_code=404, detail=f'Teklif {quotation_id} bulunamadi')
    return quotation


def _serialize(quotation: Quotation) -> dict:
    return {
        'id': quotation.id,
        'quotation_number': quotation.quotation_number,
        'customer_id': quotation.customer_id,
        'customer_name': quotation.customer.name if quotation.customer else None,
        'quotation_date': quotation.quotation_date,
        'valid_until': quotation.valid_until,
        'status': quotation.status,
        'docstatus': quotation.docstatus,
        'docstatus_label': DocStatus.LABELS.get(quotation.docstatus),
        'submitted_at': quotation.submitted_at,
        'cancelled_at': quotation.cancelled_at,
        'cancel_reason': quotation.cancel_reason,
        'subtotal': quotation.subtotal,
        'tax_total': quotation.tax_total,
        'total_amount': quotation.total_amount,
        'note': quotation.note,
        'created_at': quotation.created_at,
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
                'total_price': item.total_price,
            }
            for item in quotation.items
        ],
    }


def _build_items(db: Session, quotation: Quotation, items) -> None:
    quotation.items.clear()
    for entry in items:
        product = sales_order_service.get_product(db, entry.product_id)
        quotation.items.append(
            QuotationItem(
                product_id=product.id,
                uom_id=entry.uom_id or product.sales_uom_id or product.stock_uom_id,
                quantity=entry.quantity,
                unit_price=entry.unit_price,
                tax_rate=entry.tax_rate,
                total_price=sales_order_service.money(entry.quantity * entry.unit_price),
            )
        )
    sales_order_service.recalc_totals(quotation)


@router.post('', response_model=QuotationResponse, status_code=status.HTTP_201_CREATED)
def create_quotation(
    payload: QuotationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f'Musteri {payload.customer_id} bulunamadi')

    quotation = Quotation(
        customer_id=payload.customer_id,
        quotation_date=payload.quotation_date or date.today(),
        valid_until=payload.valid_until,
        note=payload.note,
        status='taslak',
        created_by=current_user.id,
    )
    _build_items(db, quotation, payload.items)
    db.add(quotation)
    db.flush()

    if not payload.save_as_draft:
        document_service.submit(db, quotation, user_id=current_user.id)
        quotation.status = 'gonderildi'

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Teklif kaydedilemedi: {exc}')
    return _serialize(_load(db, quotation.id))


@router.get('', response_model=list[QuotationResponse])
def list_quotations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    customer_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias='status'),
    db: Session = Depends(get_db),
):
    query = db.query(Quotation).options(
        joinedload(Quotation.customer),
        joinedload(Quotation.items).joinedload(QuotationItem.product),
        joinedload(Quotation.items).joinedload(QuotationItem.uom),
    )
    if customer_id is not None:
        query = query.filter(Quotation.customer_id == customer_id)
    if status_filter is not None:
        query = query.filter(Quotation.status == status_filter)
    quotations = query.order_by(Quotation.id.desc()).offset(skip).limit(limit).all()
    return [_serialize(q) for q in quotations]


@router.get('/{quotation_id}', response_model=QuotationResponse)
def get_quotation(quotation_id: int, db: Session = Depends(get_db)):
    return _serialize(_load(db, quotation_id))


@router.put('/{quotation_id}', response_model=QuotationResponse)
def update_quotation(
    quotation_id: int, payload: QuotationUpdate, db: Session = Depends(get_db)
):
    quotation = _load(db, quotation_id)
    document_service.ensure_editable(quotation)

    data = payload.model_dump(exclude_unset=True)
    items = data.pop('items', None)
    for field, value in data.items():
        setattr(quotation, field, value)
    if items is not None:
        _build_items(db, quotation, payload.items)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Teklif guncellenemedi: {exc}')
    return _serialize(_load(db, quotation_id))


@router.post('/{quotation_id}/submit', response_model=QuotationResponse)
def submit_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Teklifi musteriye gonderilmis olarak isaretler ve numara atar."""
    quotation = _load(db, quotation_id)
    document_service.submit(db, quotation, user_id=current_user.id)
    quotation.status = 'gonderildi'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Teklif gonderilemedi: {exc}')
    return _serialize(_load(db, quotation_id))


@router.post('/{quotation_id}/accept', response_model=QuotationResponse)
def accept_quotation(quotation_id: int, db: Session = Depends(get_db)):
    """Musteri teklifi kabul etti - siparise cevrilmeye hazir hale gelir."""
    quotation = _load(db, quotation_id)
    if quotation.docstatus != DocStatus.SUBMITTED:
        raise HTTPException(
            status_code=400, detail='Yalnizca gonderilmis teklif kabul edilebilir'
        )
    quotation.status = 'kabul'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Teklif guncellenemedi: {exc}')
    return _serialize(_load(db, quotation_id))


@router.post('/{quotation_id}/reject', response_model=QuotationResponse)
def reject_quotation(quotation_id: int, db: Session = Depends(get_db)):
    quotation = _load(db, quotation_id)
    if quotation.docstatus != DocStatus.SUBMITTED:
        raise HTTPException(
            status_code=400, detail='Yalnizca gonderilmis teklif reddedilebilir'
        )
    quotation.status = 'red'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Teklif guncellenemedi: {exc}')
    return _serialize(_load(db, quotation_id))


@router.post('/{quotation_id}/cancel', response_model=QuotationResponse)
def cancel_quotation(
    quotation_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quotation = _load(db, quotation_id)
    reason = payload.reason if payload else None
    document_service.cancel(db, quotation, user_id=current_user.id, reason=reason)
    quotation.status = 'red'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Teklif iptal edilemedi: {exc}')
    return _serialize(_load(db, quotation_id))


@router.delete('/{quotation_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_quotation(quotation_id: int, db: Session = Depends(get_db)):
    quotation = _load(db, quotation_id)
    document_service.ensure_deletable(quotation)
    try:
        db.delete(quotation)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Teklif silinemedi: {exc}')
    return None


@router.post('/{quotation_id}/to-sales-order', status_code=status.HTTP_201_CREATED)
def convert_to_sales_order(
    quotation_id: int,
    payload: QuotationToSalesOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kabul edilen teklifi siparise cevirir; kalemler birebir kopyalanir."""
    quotation = _load(db, quotation_id)
    if quotation.status != 'kabul':
        raise HTTPException(
            status_code=400,
            detail='Yalnizca kabul edilmis teklif siparise cevrilebilir',
        )

    order = SalesOrder(
        quotation_id=quotation.id,
        customer_id=quotation.customer_id,
        sale_date=date.today(),
        promised_delivery_date=payload.promised_delivery_date,
        warehouse_id=payload.warehouse_id,
        total_amount=sales_order_service.ZERO,
        status='pending',
        created_by=current_user.id,
    )
    for item in quotation.items:
        order.items.append(
            SalesOrderItem(
                product_id=item.product_id,
                uom_id=item.uom_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                tax_rate=item.tax_rate,
                total_price=item.total_price,
            )
        )
    sales_order_service.recalc_totals(order)
    db.add(order)
    db.flush()

    if not payload.save_as_draft:
        document_service.submit(db, order, user_id=current_user.id)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis olusturulamadi: {exc}')

    from .sales_orders import _load as _load_order  # gec import: dongu onlemek icin
    from .sales_orders import _serialize as _serialize_order

    return _serialize_order(_load_order(db, order.id))
