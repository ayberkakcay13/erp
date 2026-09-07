"""Depo (Warehouse) CRUD endpointleri (Phase 10)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import Product, StockLedgerEntry, User, Warehouse
from ..schemas import (
    StockBalanceRow,
    WarehouseCreate,
    WarehouseResponse,
    WarehouseUpdate,
)
from ..services import stock_service

router = APIRouter(
    prefix='/api/warehouses',
    tags=['warehouses'],
    dependencies=[Depends(get_current_user)],
)


def _get_or_404(db: Session, warehouse_id: int) -> Warehouse:
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail=f'Warehouse {warehouse_id} bulunamadi')
    return warehouse


def _clear_other_defaults(db: Session, keep_id: int | None) -> None:
    """Varsayilan depo tektir; digerlerinin bayragini indirir."""
    query = db.query(Warehouse).filter(Warehouse.is_default.is_(True))
    if keep_id is not None:
        query = query.filter(Warehouse.id != keep_id)
    for other in query.all():
        other.is_default = False


def _check_parent(db: Session, warehouse_id: int | None, parent_id: int | None) -> None:
    """Agac yapisinda kendine/donguye baglanmayi engeller."""
    if parent_id is None:
        return
    if warehouse_id is not None and parent_id == warehouse_id:
        raise HTTPException(status_code=400, detail='Depo kendi ust deposu olamaz')
    parent = db.get(Warehouse, parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail=f'Ust depo {parent_id} bulunamadi')
    seen = {warehouse_id} if warehouse_id is not None else set()
    cursor = parent
    while cursor is not None:
        if cursor.id in seen:
            raise HTTPException(status_code=400, detail='Depo agacinda dongu olusuyor')
        seen.add(cursor.id)
        cursor = db.get(Warehouse, cursor.parent_id) if cursor.parent_id else None


@router.post('', response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    _check_parent(db, None, payload.parent_id)
    warehouse = Warehouse(**payload.model_dump())
    db.add(warehouse)
    try:
        db.flush()
        if warehouse.is_default:
            _clear_other_defaults(db, warehouse.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'"{payload.code}" depo kodu zaten kayitli')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(warehouse)
    return warehouse


@router.get('', response_model=list[WarehouseResponse])
def list_warehouses(
    is_active: bool | None = Query(None, description='Sadece aktif/pasif depolar'),
    db: Session = Depends(get_db),
):
    query = db.query(Warehouse)
    if is_active is not None:
        query = query.filter(Warehouse.is_active.is_(is_active))
    return query.order_by(Warehouse.id).all()


@router.get('/{warehouse_id}', response_model=WarehouseResponse)
def get_warehouse(warehouse_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, warehouse_id)


@router.get('/{warehouse_id}/stock', response_model=list[StockBalanceRow])
def warehouse_stock(warehouse_id: int, db: Session = Depends(get_db)):
    """Depodaki urun bazli guncel stok (bakiyesi sifir olanlar da dahil)."""
    warehouse = _get_or_404(db, warehouse_id)
    balances = stock_service.get_stock_map(db, warehouse_id=warehouse_id)
    if not balances:
        return []
    products = db.query(Product).filter(Product.id.in_(balances.keys())).all()
    rows = [
        StockBalanceRow(
            product_id=p.id,
            product_name=p.name,
            sku=p.sku,
            warehouse_id=warehouse.id,
            warehouse_name=warehouse.name,
            quantity=balances.get(p.id, stock_service.ZERO),
        )
        for p in products
    ]
    rows.sort(key=lambda r: r.product_name)
    return rows


@router.put('/{warehouse_id}', response_model=WarehouseResponse)
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    warehouse = _get_or_404(db, warehouse_id)
    data = payload.model_dump(exclude_unset=True)
    if 'parent_id' in data:
        _check_parent(db, warehouse_id, data['parent_id'])
    for field, value in data.items():
        setattr(warehouse, field, value)
    if data.get('is_default'):
        _clear_other_defaults(db, warehouse.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu depo kodu baska bir depoda kayitli')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(warehouse)
    return warehouse


@router.delete('/{warehouse_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Hareket gormus depo silinmez - defterin butunlugu bozulmasin."""
    warehouse = _get_or_404(db, warehouse_id)
    has_movement = (
        db.query(StockLedgerEntry.id)
        .filter(StockLedgerEntry.warehouse_id == warehouse_id)
        .first()
        is not None
    )
    if has_movement:
        raise HTTPException(
            status_code=409,
            detail='Bu depoda stok hareketi var, silinemez. Pasife alabilirsiniz.',
        )
    if warehouse.is_default:
        raise HTTPException(status_code=409, detail='Varsayilan depo silinemez')
    try:
        db.delete(warehouse)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Depo baska kayitlarda kullaniliyor')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    return None
