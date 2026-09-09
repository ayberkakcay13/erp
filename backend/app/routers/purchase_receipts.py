"""Mal kabul endpointleri (Phase 14).

Stok hareketi yaratan TEK satin alma belgesi burasidir. Giris onay aninda
`stock_service.add_entry()` uzerinden, urunun stok biriminde yazilir.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    DocStatus,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    User,
)
from ..schemas import CancelRequest, PurchaseReceiptCreate, PurchaseReceiptResponse
from ..services import document_service, purchase_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/purchase-receipts',
    tags=['purchase-receipts'],
    dependencies=[Depends(get_current_user), Depends(require_module('purchase'))],
)


def _load(db: Session, receipt_id: int) -> PurchaseReceipt:
    receipt = (
        db.query(PurchaseReceipt)
        .options(
            joinedload(PurchaseReceipt.supplier),
            joinedload(PurchaseReceipt.order),
            joinedload(PurchaseReceipt.items).joinedload(PurchaseReceiptItem.product),
            joinedload(PurchaseReceipt.items).joinedload(PurchaseReceiptItem.uom),
        )
        .filter(PurchaseReceipt.id == receipt_id)
        .first()
    )
    if receipt is None:
        raise HTTPException(status_code=404, detail=f'Mal kabul {receipt_id} bulunamadi')
    return receipt


def _serialize(receipt: PurchaseReceipt) -> dict:
    return {
        'id': receipt.id,
        'receipt_number': receipt.receipt_number,
        'purchase_order_id': receipt.purchase_order_id,
        'po_number': receipt.order.po_number if receipt.order else None,
        'supplier_id': receipt.supplier_id,
        'supplier_name': receipt.supplier.name if receipt.supplier else None,
        'warehouse_id': receipt.warehouse_id,
        'receipt_date': receipt.receipt_date,
        'docstatus': receipt.docstatus,
        'docstatus_label': DocStatus.LABELS.get(receipt.docstatus),
        'submitted_at': receipt.submitted_at,
        'cancelled_at': receipt.cancelled_at,
        'cancel_reason': receipt.cancel_reason,
        'note': receipt.note,
        'created_at': receipt.created_at,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
                'purchase_order_item_id': item.purchase_order_item_id,
                'uom_id': item.uom_id,
                'uom_code': item.uom.code if item.uom else None,
                'quantity': item.quantity,
                'accepted_quantity': item.accepted_quantity,
                'rejected_quantity': item.rejected_quantity,
                'stock_quantity': item.stock_quantity,
                'unit_price': item.unit_price,
                'reject_reason': item.reject_reason,
            }
            for item in receipt.items
        ],
    }


def _order_item_for(db: Session, receipt: PurchaseReceipt, entry) -> PurchaseOrderItem:
    if entry.purchase_order_item_id is None:
        return None
    order_item = db.get(PurchaseOrderItem, entry.purchase_order_item_id)
    if order_item is None:
        raise HTTPException(
            status_code=404,
            detail=f'Siparis kalemi {entry.purchase_order_item_id} bulunamadi',
        )
    if (
        receipt.purchase_order_id is not None
        and order_item.purchase_order_id != receipt.purchase_order_id
    ):
        raise HTTPException(
            status_code=400, detail='Siparis kalemi bu siparise ait degil'
        )
    return order_item


def _build_items(db: Session, receipt: PurchaseReceipt, items) -> None:
    receipt.items.clear()
    for entry in items:
        product = purchase_service.get_product(db, entry.product_id)
        uom_id = entry.uom_id or product.purchase_uom_id or product.stock_uom_id
        accepted = (
            entry.quantity if entry.accepted_quantity is None else entry.accepted_quantity
        )
        rejected = entry.rejected_quantity
        if purchase_service.to_decimal(accepted) + purchase_service.to_decimal(
            rejected
        ) > purchase_service.to_decimal(entry.quantity):
            raise HTTPException(
                status_code=400,
                detail=(
                    f'"{product.name}": kabul + red miktari gelen miktari asamaz'
                ),
            )

        order_item = _order_item_for(db, receipt, entry)
        if order_item is not None:
            purchase_service.ensure_not_over_receipt(db, order_item, accepted, uom_id)

        receipt.items.append(
            PurchaseReceiptItem(
                purchase_order_item_id=entry.purchase_order_item_id,
                product_id=product.id,
                uom_id=uom_id,
                quantity=entry.quantity,
                accepted_quantity=accepted,
                rejected_quantity=rejected,
                stock_quantity=purchase_service.stock_quantity_for(
                    db, product, accepted, uom_id
                ),
                unit_price=entry.unit_price,
                reject_reason=entry.reject_reason,
            )
        )


@router.post(
    '', response_model=PurchaseReceiptResponse, status_code=status.HTTP_201_CREATED
)
def create_receipt(
    payload: PurchaseReceiptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    purchase_service.get_supplier(db, payload.supplier_id)
    warehouse_id = payload.warehouse_id
    order = None
    if payload.purchase_order_id is not None:
        order = db.get(PurchaseOrder, payload.purchase_order_id)
        if order is None:
            raise HTTPException(
                status_code=404,
                detail=f'Siparis {payload.purchase_order_id} bulunamadi',
            )
        if order.docstatus != DocStatus.SUBMITTED:
            raise HTTPException(
                status_code=400, detail='Yalnizca onayli siparisten mal kabul yapilabilir'
            )
        if warehouse_id is None:
            warehouse_id = order.warehouse_id
    purchase_service.ensure_warehouse(db, warehouse_id)

    receipt = PurchaseReceipt(
        purchase_order_id=payload.purchase_order_id,
        supplier_id=payload.supplier_id,
        warehouse_id=warehouse_id,
        receipt_date=payload.receipt_date or date.today(),
        note=payload.note,
        created_by=current_user.id,
    )
    _build_items(db, receipt, payload.items)
    db.add(receipt)
    db.flush()

    if not payload.save_as_draft:
        document_service.submit(db, receipt, user_id=current_user.id)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Mal kabul kaydedilemedi: {exc}')
    return _serialize(_load(db, receipt.id))


@router.get('', response_model=list[PurchaseReceiptResponse])
def list_receipts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    supplier_id: int | None = Query(None),
    purchase_order_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(PurchaseReceipt).options(
        joinedload(PurchaseReceipt.supplier),
        joinedload(PurchaseReceipt.order),
        joinedload(PurchaseReceipt.items).joinedload(PurchaseReceiptItem.product),
        joinedload(PurchaseReceipt.items).joinedload(PurchaseReceiptItem.uom),
    )
    if supplier_id is not None:
        query = query.filter(PurchaseReceipt.supplier_id == supplier_id)
    if purchase_order_id is not None:
        query = query.filter(PurchaseReceipt.purchase_order_id == purchase_order_id)
    receipts = query.order_by(PurchaseReceipt.id.desc()).offset(skip).limit(limit).all()
    return [_serialize(receipt) for receipt in receipts]


@router.get('/from-order/{order_id}')
def draft_from_order(order_id: int, db: Session = Depends(get_db)):
    """Siparisten mal kabul taslagi: kalan miktarlarla kalem listesi doner."""
    order = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.product),
            joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.uom),
        )
        .filter(PurchaseOrder.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail=f'Siparis {order_id} bulunamadi')

    items = []
    for item in order.items:
        pending = purchase_service.remaining(item)
        if pending <= purchase_service.ZERO:
            continue
        items.append({
            'purchase_order_item_id': item.id,
            'product_id': item.product_id,
            'product_name': item.product.name if item.product else None,
            'product_sku': item.product.sku if item.product else None,
            'uom_id': item.uom_id,
            'uom_code': item.uom.code if item.uom else None,
            'quantity': pending,
            'accepted_quantity': pending,
            'rejected_quantity': purchase_service.ZERO,
            'unit_price': item.unit_price,
        })

    return {
        'purchase_order_id': order.id,
        'po_number': order.po_number,
        'supplier_id': order.supplier_id,
        'warehouse_id': order.warehouse_id,
        'items': items,
    }


@router.get('/{receipt_id}', response_model=PurchaseReceiptResponse)
def get_receipt(receipt_id: int, db: Session = Depends(get_db)):
    return _serialize(_load(db, receipt_id))


@router.post('/{receipt_id}/submit', response_model=PurchaseReceiptResponse)
def submit_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mal kabulu onaylar: stok bu anda artar, ledger'a `alim` kaydi duser."""
    receipt = _load(db, receipt_id)
    document_service.submit(db, receipt, user_id=current_user.id)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Mal kabul onaylanamadi: {exc}')
    return _serialize(_load(db, receipt_id))


@router.post('/{receipt_id}/cancel', response_model=PurchaseReceiptResponse)
def cancel_receipt(
    receipt_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mal kabulu iptal eder: ters ledger kaydi (`alim_iade`) olusur."""
    receipt = _load(db, receipt_id)
    reason = payload.reason if payload else None
    document_service.cancel(db, receipt, user_id=current_user.id, reason=reason)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Mal kabul iptal edilemedi: {exc}')
    return _serialize(_load(db, receipt_id))


@router.delete('/{receipt_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_receipt(receipt_id: int, db: Session = Depends(get_db)):
    receipt = _load(db, receipt_id)
    document_service.ensure_deletable(receipt)
    try:
        db.delete(receipt)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Mal kabul silinemedi: {exc}')
    return None
