"""Sevkiyat irsaliyesi endpointleri (Phase 15).

STOK HAREKETI YARATAN TEK satis belgesi burasidir. Onay aninda her kalem
icin `stock_service.add_entry()` cagrilir (reason='satis',
ref_type='delivery'), urunun stok biriminde.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Customer,
    DeliveryNote,
    DeliveryNoteItem,
    DocStatus,
    SalesOrder,
    SalesOrderItem,
    User,
)
from ..schemas import CancelRequest, DeliveryNoteCreate, DeliveryNoteResponse
from ..services import document_service, sales_order_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/delivery-notes',
    tags=['delivery-notes'],
    dependencies=[Depends(get_current_user), Depends(require_module('sales'))],
)


def _load(db: Session, delivery_note_id: int) -> DeliveryNote:
    delivery_note = (
        db.query(DeliveryNote)
        .options(
            joinedload(DeliveryNote.customer),
            joinedload(DeliveryNote.sales_order),
            joinedload(DeliveryNote.items).joinedload(DeliveryNoteItem.product),
            joinedload(DeliveryNote.items).joinedload(DeliveryNoteItem.uom),
        )
        .filter(DeliveryNote.id == delivery_note_id)
        .first()
    )
    if delivery_note is None:
        raise HTTPException(status_code=404, detail=f'Sevkiyat {delivery_note_id} bulunamadi')
    return delivery_note


def _serialize(delivery_note: DeliveryNote) -> dict:
    return {
        'id': delivery_note.id,
        'delivery_note_number': delivery_note.delivery_note_number,
        'sales_order_id': delivery_note.sales_order_id,
        'so_number': delivery_note.sales_order.so_number if delivery_note.sales_order else None,
        'customer_id': delivery_note.customer_id,
        'customer_name': delivery_note.customer.name if delivery_note.customer else None,
        'warehouse_id': delivery_note.warehouse_id,
        'delivery_date': delivery_note.delivery_date,
        'docstatus': delivery_note.docstatus,
        'docstatus_label': DocStatus.LABELS.get(delivery_note.docstatus),
        'submitted_at': delivery_note.submitted_at,
        'cancelled_at': delivery_note.cancelled_at,
        'cancel_reason': delivery_note.cancel_reason,
        'note': delivery_note.note,
        'created_at': delivery_note.created_at,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
                'sales_order_item_id': item.sales_order_item_id,
                'uom_id': item.uom_id,
                'uom_code': item.uom.code if item.uom else None,
                'warehouse_id': item.warehouse_id,
                'quantity': item.quantity,
                'stock_quantity': item.stock_quantity,
                'unit_price': item.unit_price,
                'item_status': item.item_status,
            }
            for item in delivery_note.items
        ],
    }


def _order_item_for(db: Session, delivery_note: DeliveryNote, entry) -> SalesOrderItem | None:
    if entry.sales_order_item_id is None:
        return None
    order_item = db.get(SalesOrderItem, entry.sales_order_item_id)
    if order_item is None:
        raise HTTPException(
            status_code=404,
            detail=f'Siparis kalemi {entry.sales_order_item_id} bulunamadi',
        )
    if (
        delivery_note.sales_order_id is not None
        and order_item.sales_order_id != delivery_note.sales_order_id
    ):
        raise HTTPException(status_code=400, detail='Siparis kalemi bu siparise ait degil')
    return order_item


def _build_items(db: Session, delivery_note: DeliveryNote, items) -> None:
    delivery_note.items.clear()
    for entry in items:
        product = sales_order_service.get_product(db, entry.product_id)
        uom_id = entry.uom_id or product.sales_uom_id or product.stock_uom_id

        order_item = _order_item_for(db, delivery_note, entry)
        if order_item is not None:
            sales_order_service.ensure_not_over_delivery(db, order_item, entry.quantity, uom_id)

        delivery_note.items.append(
            DeliveryNoteItem(
                sales_order_item_id=entry.sales_order_item_id,
                product_id=product.id,
                uom_id=uom_id,
                warehouse_id=entry.warehouse_id,
                quantity=entry.quantity,
                unit_price=entry.unit_price,
                stock_quantity=sales_order_service.stock_quantity_for(
                    db, product, entry.quantity, uom_id
                ),
                item_status=entry.item_status,
            )
        )


@router.post('', response_model=DeliveryNoteResponse, status_code=status.HTTP_201_CREATED)
def create_delivery_note(
    payload: DeliveryNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail=f'Musteri {payload.customer_id} bulunamadi')

    order = None
    if payload.sales_order_id is not None:
        order = db.get(SalesOrder, payload.sales_order_id)
        if order is None:
            raise HTTPException(
                status_code=404, detail=f'Siparis {payload.sales_order_id} bulunamadi'
            )
        if order.docstatus != DocStatus.SUBMITTED:
            raise HTTPException(
                status_code=400, detail='Yalnizca onayli siparisten sevkiyat yapilabilir'
            )

    delivery_note = DeliveryNote(
        sales_order_id=payload.sales_order_id,
        customer_id=payload.customer_id,
        warehouse_id=payload.warehouse_id or (order.warehouse_id if order else None),
        delivery_date=payload.delivery_date or date.today(),
        note=payload.note,
        created_by=current_user.id,
    )
    _build_items(db, delivery_note, payload.items)
    db.add(delivery_note)
    db.flush()

    if not payload.save_as_draft:
        document_service.submit(db, delivery_note, user_id=current_user.id)
        if order is not None:
            sales_order_service.refresh_delivery_status(db, order)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Sevkiyat kaydedilemedi: {exc}')
    return _serialize(_load(db, delivery_note.id))


@router.get('', response_model=list[DeliveryNoteResponse])
def list_delivery_notes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    customer_id: int | None = Query(None),
    sales_order_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(DeliveryNote).options(
        joinedload(DeliveryNote.customer),
        joinedload(DeliveryNote.sales_order),
        joinedload(DeliveryNote.items).joinedload(DeliveryNoteItem.product),
        joinedload(DeliveryNote.items).joinedload(DeliveryNoteItem.uom),
    )
    if customer_id is not None:
        query = query.filter(DeliveryNote.customer_id == customer_id)
    if sales_order_id is not None:
        query = query.filter(DeliveryNote.sales_order_id == sales_order_id)
    notes = query.order_by(DeliveryNote.id.desc()).offset(skip).limit(limit).all()
    return [_serialize(note) for note in notes]


@router.get('/from-order/{order_id}')
def draft_from_order(order_id: int, db: Session = Depends(get_db)):
    """Siparisten sevkiyat taslagi: kalan miktarlarla kalem listesi doner."""
    order = (
        db.query(SalesOrder)
        .options(
            joinedload(SalesOrder.items).joinedload(SalesOrderItem.product),
            joinedload(SalesOrder.items).joinedload(SalesOrderItem.uom),
        )
        .filter(SalesOrder.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail=f'Siparis {order_id} bulunamadi')

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
            'warehouse_id': item.warehouse_id,
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


@router.get('/{delivery_note_id}/invoice-draft')
def invoice_draft(delivery_note_id: int, db: Session = Depends(get_db)):
    """Onayli sevkiyattan fatura taslagi: kalemler birebir kopyalanir."""
    delivery_note = _load(db, delivery_note_id)
    if delivery_note.docstatus != DocStatus.SUBMITTED:
        raise HTTPException(
            status_code=400, detail='Yalnizca onayli sevkiyattan fatura taslagi cikarilabilir'
        )
    return {
        'delivery_note_id': delivery_note.id,
        'customer_id': delivery_note.customer_id,
        'items': [
            {
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
                'uom_id': item.uom_id,
                'uom_code': item.uom.code if item.uom else None,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
            }
            for item in delivery_note.items
        ],
    }


@router.get('/{delivery_note_id}', response_model=DeliveryNoteResponse)
def get_delivery_note(delivery_note_id: int, db: Session = Depends(get_db)):
    return _serialize(_load(db, delivery_note_id))


@router.post('/{delivery_note_id}/submit', response_model=DeliveryNoteResponse)
def submit_delivery_note(
    delivery_note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sevkiyati onaylar: stok bu anda duser, ledger'a `satis` kaydi duser."""
    delivery_note = _load(db, delivery_note_id)
    document_service.submit(db, delivery_note, user_id=current_user.id)
    if delivery_note.sales_order_id is not None:
        order = db.get(SalesOrder, delivery_note.sales_order_id)
        if order is not None:
            sales_order_service.refresh_delivery_status(db, order)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Sevkiyat onaylanamadi: {exc}')
    return _serialize(_load(db, delivery_note_id))


@router.post('/{delivery_note_id}/cancel', response_model=DeliveryNoteResponse)
def cancel_delivery_note(
    delivery_note_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sevkiyati iptal eder: ters ledger kaydi (`satis_iptal`) olusur."""
    delivery_note = _load(db, delivery_note_id)
    reason = payload.reason if payload else None
    document_service.cancel(db, delivery_note, user_id=current_user.id, reason=reason)
    if delivery_note.sales_order_id is not None:
        order = db.get(SalesOrder, delivery_note.sales_order_id)
        if order is not None:
            sales_order_service.refresh_delivery_status(db, order)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Sevkiyat iptal edilemedi: {exc}')
    return _serialize(_load(db, delivery_note_id))


@router.delete('/{delivery_note_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_delivery_note(delivery_note_id: int, db: Session = Depends(get_db)):
    delivery_note = _load(db, delivery_note_id)
    document_service.ensure_deletable(delivery_note)
    try:
        db.delete(delivery_note)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Sevkiyat silinemedi: {exc}')
    return None
