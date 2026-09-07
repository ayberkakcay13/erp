"""Stok defteri okuma endpointleri ve elle duzeltme girisi (Phase 10)."""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import Product, StockLedgerEntry, User, Warehouse
from ..schemas import (
    StockAdjustment,
    StockBalanceRow,
    StockLedgerEntryResponse,
)
from ..services import stock_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/stock',
    tags=['stock'],
    dependencies=[Depends(get_current_user), Depends(require_module('stock'))],
)


def _serialize_entry(entry: StockLedgerEntry) -> dict:
    return {
        'id': entry.id,
        'product_id': entry.product_id,
        'warehouse_id': entry.warehouse_id,
        'change_qty': entry.change_qty,
        'balance_qty': entry.balance_qty,
        'reason': entry.reason,
        'ref_type': entry.ref_type,
        'ref_id': entry.ref_id,
        'note': entry.note,
        'created_by': entry.created_by,
        'created_at': entry.created_at,
        'product_name': entry.product.name if entry.product else None,
        'product_sku': entry.product.sku if entry.product else None,
        'warehouse_name': entry.warehouse.name if entry.warehouse else None,
    }


@router.get('/balance', response_model=list[StockBalanceRow])
def stock_balance(
    product_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Urun x depo bazli guncel stok.

    warehouse_id verilmezse her (urun, depo) kirilimi ayri satir olarak doner.
    """
    from sqlalchemy import func, select

    query = select(
        StockLedgerEntry.product_id,
        StockLedgerEntry.warehouse_id,
        func.coalesce(func.sum(StockLedgerEntry.change_qty), 0),
    ).group_by(StockLedgerEntry.product_id, StockLedgerEntry.warehouse_id)
    if product_id is not None:
        query = query.where(StockLedgerEntry.product_id == product_id)
    if warehouse_id is not None:
        query = query.where(StockLedgerEntry.warehouse_id == warehouse_id)

    rows = db.execute(query).all()
    if not rows:
        return []

    products = {
        p.id: p
        for p in db.query(Product).filter(Product.id.in_({r[0] for r in rows})).all()
    }
    warehouses = {
        w.id: w
        for w in db.query(Warehouse).filter(Warehouse.id.in_({r[1] for r in rows})).all()
    }

    result = []
    for pid, wid, qty in rows:
        product = products.get(pid)
        warehouse = warehouses.get(wid)
        if product is None:
            continue
        result.append(
            StockBalanceRow(
                product_id=pid,
                product_name=product.name,
                sku=product.sku,
                warehouse_id=wid,
                warehouse_name=warehouse.name if warehouse else None,
                quantity=stock_service.to_decimal(qty or 0),
            )
        )
    result.sort(key=lambda r: (r.product_name, r.warehouse_name or ''))
    return result


@router.get('/ledger', response_model=list[StockLedgerEntryResponse])
def stock_ledger(
    product_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    reason: str | None = Query(None),
    date_from: date | None = Query(None, alias='from'),
    date_to: date | None = Query(None, alias='to'),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Hareket dokumu. En yeni hareket once gelir."""
    query = db.query(StockLedgerEntry).options(
        joinedload(StockLedgerEntry.product),
        joinedload(StockLedgerEntry.warehouse),
    )
    if product_id is not None:
        query = query.filter(StockLedgerEntry.product_id == product_id)
    if warehouse_id is not None:
        query = query.filter(StockLedgerEntry.warehouse_id == warehouse_id)
    if reason is not None:
        query = query.filter(StockLedgerEntry.reason == reason)
    if date_from is not None:
        query = query.filter(StockLedgerEntry.created_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        query = query.filter(StockLedgerEntry.created_at <= datetime.combine(date_to, time.max))

    entries = (
        query.order_by(StockLedgerEntry.created_at.desc(), StockLedgerEntry.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_serialize_entry(e) for e in entries]


@router.get('/product/{product_id}/history')
def product_stock_history(
    product_id: int,
    warehouse_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Tek urunun stok hareket gecmisi + depo bazli guncel bakiyeleri."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f'Product {product_id} bulunamadi')

    query = db.query(StockLedgerEntry).options(
        joinedload(StockLedgerEntry.warehouse), joinedload(StockLedgerEntry.product)
    ).filter(StockLedgerEntry.product_id == product_id)
    if warehouse_id is not None:
        query = query.filter(StockLedgerEntry.warehouse_id == warehouse_id)
    entries = (
        query.order_by(StockLedgerEntry.created_at.desc(), StockLedgerEntry.id.desc())
        .limit(limit)
        .all()
    )

    by_warehouse = stock_balance(product_id=product_id, warehouse_id=None, db=db)
    return {
        'product_id': product.id,
        'product_name': product.name,
        'sku': product.sku,
        'total_stock': stock_service.get_stock(db, product_id),
        'by_warehouse': [row.model_dump() for row in by_warehouse],
        'entries': [_serialize_entry(e) for e in entries],
    }


@router.post('/adjustments', response_model=StockLedgerEntryResponse,
             status_code=status.HTTP_201_CREATED)
def create_adjustment(
    payload: StockAdjustment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Elle stok duzeltme / sayim / fire girisi.

    Ledger satiri duzeltilmez; her duzeltme yeni bir satirdir.
    """
    entry = stock_service.add_entry(
        db,
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
        change_qty=payload.change_qty,
        reason=payload.reason,
        ref_type='adjustment',
        ref_id=None,
        user_id=current_user.id,
        note=payload.note,
    )
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Stok duzeltmesi kaydedilemedi: {exc}')
    db.refresh(entry)
    return _serialize_entry(entry)
