"""Satin alma siparisi endpointleri (Phase 14).

Siparis niyet beyanidir: onaylanmasi stok hareketi yaratmaz. Stok yalnizca
mal kabulde hareket eder.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import DocStatus, PurchaseOrder, PurchaseOrderItem, User
from ..schemas import (
    CancelRequest,
    PurchaseMatchResponse,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
)
from ..services import document_service, purchase_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/purchase-orders',
    tags=['purchase-orders'],
    dependencies=[Depends(get_current_user), Depends(require_module('purchase'))],
)

match_router = APIRouter(
    prefix='/api/purchase',
    tags=['purchase-orders'],
    dependencies=[Depends(get_current_user), Depends(require_module('purchase'))],
)


def _load(db: Session, order_id: int) -> PurchaseOrder:
    order = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.supplier),
            joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.product),
            joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.uom),
        )
        .filter(PurchaseOrder.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail=f'Siparis {order_id} bulunamadi')
    return order


def _serialize(order: PurchaseOrder) -> dict:
    return {
        'id': order.id,
        'po_number': order.po_number,
        'supplier_id': order.supplier_id,
        'supplier_name': order.supplier.name if order.supplier else None,
        'order_date': order.order_date,
        'expected_date': order.expected_date,
        'warehouse_id': order.warehouse_id,
        'status': order.status,
        'docstatus': order.docstatus,
        'docstatus_label': DocStatus.LABELS.get(order.docstatus),
        'submitted_at': order.submitted_at,
        'cancelled_at': order.cancelled_at,
        'cancel_reason': order.cancel_reason,
        'subtotal': order.subtotal,
        'tax_total': order.tax_total,
        'grand_total': order.grand_total,
        'note': order.note,
        'created_at': order.created_at,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
                'uom_id': item.uom_id,
                'uom_code': item.uom.code if item.uom else None,
                'quantity': item.quantity,
                'received_quantity': item.received_quantity,
                'remaining_quantity': purchase_service.remaining(item),
                'unit_price': item.unit_price,
                'tax_rate': item.tax_rate,
                'line_total': item.line_total,
            }
            for item in order.items
        ],
    }


def _build_items(db: Session, order: PurchaseOrder, items) -> None:
    order.items.clear()
    for entry in items:
        product = purchase_service.get_product(db, entry.product_id)
        order.items.append(
            PurchaseOrderItem(
                product_id=product.id,
                uom_id=entry.uom_id or product.purchase_uom_id or product.stock_uom_id,
                quantity=entry.quantity,
                received_quantity=purchase_service.ZERO,
                unit_price=entry.unit_price,
                tax_rate=entry.tax_rate,
            )
        )
    purchase_service.recalc_totals(order)


@router.post('', response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    purchase_service.get_supplier(db, payload.supplier_id)
    purchase_service.ensure_warehouse(db, payload.warehouse_id)

    order = PurchaseOrder(
        supplier_id=payload.supplier_id,
        order_date=payload.order_date or date.today(),
        expected_date=payload.expected_date,
        warehouse_id=payload.warehouse_id,
        status='beklemede',
        note=payload.note,
        created_by=current_user.id,
    )
    _build_items(db, order, payload.items)
    db.add(order)
    db.flush()

    if not payload.save_as_draft:
        document_service.submit(db, order, user_id=current_user.id)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis kaydedilemedi: {exc}')
    return _serialize(_load(db, order.id))


@router.get('', response_model=list[PurchaseOrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    supplier_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias='status'),
    db: Session = Depends(get_db),
):
    query = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.supplier),
        joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.product),
        joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.uom),
    )
    if supplier_id is not None:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)
    if status_filter is not None:
        query = query.filter(PurchaseOrder.status == status_filter)
    orders = query.order_by(PurchaseOrder.id.desc()).offset(skip).limit(limit).all()
    return [_serialize(order) for order in orders]


@router.get('/{order_id}', response_model=PurchaseOrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return _serialize(_load(db, order_id))


@router.put('/{order_id}', response_model=PurchaseOrderResponse)
def update_order(
    order_id: int, payload: PurchaseOrderUpdate, db: Session = Depends(get_db)
):
    order = _load(db, order_id)
    document_service.ensure_editable(order)

    data = payload.model_dump(exclude_unset=True)
    items = data.pop('items', None)
    if 'supplier_id' in data:
        purchase_service.get_supplier(db, data['supplier_id'])
    if 'warehouse_id' in data:
        purchase_service.ensure_warehouse(db, data['warehouse_id'])
    for field, value in data.items():
        setattr(order, field, value)
    if items is not None:
        _build_items(db, order, payload.items)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis guncellenemedi: {exc}')
    return _serialize(_load(db, order_id))


@router.post('/{order_id}/submit', response_model=PurchaseOrderResponse)
def submit_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Siparisi onaylar ve numarasini atar. Stok hareketi olusmaz."""
    order = _load(db, order_id)
    document_service.submit(db, order, user_id=current_user.id)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis onaylanamadi: {exc}')
    return _serialize(_load(db, order_id))


@router.post('/{order_id}/cancel', response_model=PurchaseOrderResponse)
def cancel_order(
    order_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _load(db, order_id)
    if any(purchase_service.to_decimal(i.received_quantity) > purchase_service.ZERO
           for i in order.items):
        raise HTTPException(
            status_code=400,
            detail=(
                'Mal kabulu yapilmis siparis iptal edilemez. '
                'Once ilgili mal kabullerini iptal edin.'
            ),
        )
    reason = payload.reason if payload else None
    document_service.cancel(db, order, user_id=current_user.id, reason=reason)
    order.status = 'iptal'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis iptal edilemedi: {exc}')
    return _serialize(_load(db, order_id))


@router.delete('/{order_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = _load(db, order_id)
    document_service.ensure_deletable(order)
    try:
        db.delete(order)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis silinemedi: {exc}')
    return None


@match_router.get('/match/{order_id}', response_model=PurchaseMatchResponse)
def purchase_match(order_id: int, db: Session = Depends(get_db)):
    """Uclu eslestirme: siparis / mal kabul / fatura karsilastirmasi."""
    order = _load(db, order_id)
    return purchase_service.three_way_match(db, order)
