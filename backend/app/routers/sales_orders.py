"""Satis siparisi endpointleri (Phase 15 - yeni akis).

Bu router `Quotation -> SalesOrder -> DeliveryNote` zincirinin siparis
adimidir. `/api/sales` (Phase 10-14 uyum katmani) ile ayni tabloyu
(`sales_orders`) kullanir ama farkli bir sozlesme sunar: kredi limiti
kontrolu, teklif baglantisi, ve durumun `confirmed/partially_delivered/
delivered` olarak ilerlemesi.

Siparis onayi STOK HAREKETI YARATMAZ - niyet beyanidir. Stok yalnizca
DeliveryNote onayinda hareket eder.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import Customer, DocStatus, Product, SalesOrder, SalesOrderItem, User
from ..schemas import CancelRequest, SalesOrderCreate, SalesOrderResponse
from ..services import credit_service, document_service, sales_order_service, uom_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/sales-orders',
    tags=['sales-orders'],
    dependencies=[Depends(get_current_user), Depends(require_module('sales'))],
)


def _load(db: Session, order_id: int) -> SalesOrder:
    order = (
        db.query(SalesOrder)
        .options(
            joinedload(SalesOrder.customer),
            joinedload(SalesOrder.items).joinedload(SalesOrderItem.product),
            joinedload(SalesOrder.items).joinedload(SalesOrderItem.uom),
        )
        .filter(SalesOrder.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail=f'Siparis {order_id} bulunamadi')
    return order


def _serialize(order: SalesOrder, credit_warning: dict | None = None) -> dict:
    return {
        'id': order.id,
        'customer_id': order.customer_id,
        'sale_date': order.sale_date,
        'so_number': order.so_number,
        'quotation_id': order.quotation_id,
        'promised_delivery_date': order.promised_delivery_date,
        'warehouse_id': order.warehouse_id,
        'subtotal': order.subtotal,
        'tax_total': order.tax_total,
        'total_amount': order.total_amount,
        'status': order.status,
        'docstatus': order.docstatus,
        'docstatus_label': DocStatus.LABELS.get(order.docstatus),
        'submitted_at': order.submitted_at,
        'submitted_by': order.submitted_by,
        'cancelled_at': order.cancelled_at,
        'cancelled_by': order.cancelled_by,
        'cancel_reason': order.cancel_reason,
        'created_at': order.created_at,
        'customer': order.customer,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'tax_rate': item.tax_rate,
                'total_price': item.total_price,
                'warehouse_id': item.warehouse_id,
                'uom_id': item.uom_id,
                'uom_code': item.uom.code if item.uom else None,
                'stock_quantity': item.stock_quantity,
                'delivered_quantity': item.delivered_quantity,
                'remaining_quantity': sales_order_service.remaining(item),
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
            }
            for item in order.items
        ],
        'credit_warning': credit_warning,
    }


def _build_items(db: Session, order: SalesOrder, items) -> None:
    order.items.clear()
    for entry in items:
        product = sales_order_service.get_product(db, entry.product_id)
        uom_id = entry.uom_id or product.sales_uom_id or product.stock_uom_id
        qty = entry.quantity
        order.items.append(
            SalesOrderItem(
                product_id=product.id,
                uom_id=uom_id,
                warehouse_id=entry.warehouse_id,
                quantity=qty,
                unit_price=entry.unit_price,
                tax_rate=entry.tax_rate,
                total_price=sales_order_service.money(qty * entry.unit_price),
                stock_quantity=uom_service.to_stock_uom(db, product, qty, entry.uom_id),
                delivered_quantity=sales_order_service.ZERO,
            )
        )
    sales_order_service.recalc_totals(order)


@router.post('', response_model=SalesOrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f'Musteri {payload.customer_id} bulunamadi')

    order = SalesOrder(
        quotation_id=payload.quotation_id,
        customer_id=payload.customer_id,
        sale_date=payload.sale_date or date.today(),
        promised_delivery_date=payload.promised_delivery_date,
        warehouse_id=payload.warehouse_id,
        total_amount=sales_order_service.ZERO,
        status='pending',
        created_by=current_user.id,
    )
    _build_items(db, order, payload.items)
    db.add(order)
    db.flush()

    credit_warning = None
    if not payload.save_as_draft:
        check = credit_service.check_credit(
            db, order.customer_id, order.total_amount,
            block_if_exceeded=payload.block_if_credit_exceeded,
        )
        if not check['allowed']:
            credit_warning = check
        document_service.submit(db, order, user_id=current_user.id)
        order.status = 'confirmed'

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis kaydedilemedi: {exc}')
    return _serialize(_load(db, order.id), credit_warning)


@router.get('', response_model=list[SalesOrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    customer_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias='status'),
    db: Session = Depends(get_db),
):
    query = db.query(SalesOrder).options(
        joinedload(SalesOrder.customer),
        joinedload(SalesOrder.items).joinedload(SalesOrderItem.product),
        joinedload(SalesOrder.items).joinedload(SalesOrderItem.uom),
    )
    if customer_id is not None:
        query = query.filter(SalesOrder.customer_id == customer_id)
    if status_filter is not None:
        query = query.filter(SalesOrder.status == status_filter)
    orders = query.order_by(SalesOrder.id.desc()).offset(skip).limit(limit).all()
    return [_serialize(order) for order in orders]


@router.get('/{order_id}', response_model=SalesOrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return _serialize(_load(db, order_id))


@router.get('/{order_id}/deliverable-items')
def deliverable_items(order_id: int, db: Session = Depends(get_db)):
    """Siparisin kalan (sevk edilmeyi bekleyen) kalemlerini doner."""
    order = _load(db, order_id)
    items = []
    for item in order.items:
        pending = sales_order_service.remaining(item)
        if pending <= sales_order_service.ZERO:
            continue
        items.append({
            'sales_order_item_id': item.id,
            'product_id': item.product_id,
            'product_name': item.product.name if item.product else None,
            'product_sku': item.product.sku if item.product else None,
            'uom_id': item.uom_id,
            'uom_code': item.uom.code if item.uom else None,
            'quantity': pending,
            'unit_price': item.unit_price,
        })
    return {
        'sales_order_id': order.id,
        'so_number': order.so_number,
        'customer_id': order.customer_id,
        'warehouse_id': order.warehouse_id,
        'items': items,
    }


@router.put('/{order_id}', response_model=SalesOrderResponse)
def update_order(order_id: int, payload: SalesOrderCreate, db: Session = Depends(get_db)):
    order = _load(db, order_id)
    document_service.ensure_editable(order)

    if db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail=f'Musteri {payload.customer_id} bulunamadi')

    order.customer_id = payload.customer_id
    order.sale_date = payload.sale_date or order.sale_date
    order.promised_delivery_date = payload.promised_delivery_date
    order.warehouse_id = payload.warehouse_id
    order.quotation_id = payload.quotation_id
    _build_items(db, order, payload.items)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis guncellenemedi: {exc}')
    return _serialize(_load(db, order_id))


@router.post('/{order_id}/submit', response_model=SalesOrderResponse)
def submit_order(
    order_id: int,
    block_if_credit_exceeded: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Siparisi onaylar ve numarasini atar. Stok hareketi olusmaz."""
    order = _load(db, order_id)
    check = credit_service.check_credit(
        db, order.customer_id, order.total_amount, block_if_exceeded=block_if_credit_exceeded
    )
    document_service.submit(db, order, user_id=current_user.id)
    order.status = 'confirmed'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Siparis onaylanamadi: {exc}')
    return _serialize(_load(db, order_id), None if check['allowed'] else check)


@router.post('/{order_id}/cancel', response_model=SalesOrderResponse)
def cancel_order(
    order_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _load(db, order_id)
    if any(sales_order_service.to_decimal(i.delivered_quantity) > sales_order_service.ZERO
           for i in order.items):
        raise HTTPException(
            status_code=400,
            detail=(
                'Sevkiyati yapilmis siparis iptal edilemez. '
                'Once ilgili sevkiyatlari iptal edin.'
            ),
        )
    reason = payload.reason if payload else None
    document_service.cancel(db, order, user_id=current_user.id, reason=reason)
    order.status = 'cancelled'
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
