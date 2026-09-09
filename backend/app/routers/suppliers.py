"""Tedarikci CRUD endpointleri (Phase 14)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import Supplier, User
from ..schemas import SupplierCreate, SupplierResponse, SupplierUpdate
from ..services import purchase_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/suppliers',
    tags=['suppliers'],
    dependencies=[Depends(get_current_user), Depends(require_module('purchase'))],
)


def _get_or_404(db: Session, supplier_id: int) -> Supplier:
    return purchase_service.get_supplier(db, supplier_id)


@router.post('', response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db)):
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f'"{payload.code}" tedarikci kodu zaten kayitli'
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(supplier)
    return supplier


@router.get('', response_model=list[SupplierResponse])
def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Supplier)
    if is_active is not None:
        query = query.filter(Supplier.is_active.is_(is_active))
    return query.order_by(Supplier.name).offset(skip).limit(limit).all()


@router.get('/{supplier_id}', response_model=SupplierResponse)
def get_supplier(supplier_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, supplier_id)


@router.put('/{supplier_id}', response_model=SupplierResponse)
def update_supplier(
    supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db)
):
    supplier = _get_or_404(db, supplier_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail='Bu tedarikci kodu baska bir tedarikcide kayitli'
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(supplier)
    return supplier


@router.delete('/{supplier_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Satin alma kaydi olan tedarikci silinemez, pasife alinir."""
    supplier = _get_or_404(db, supplier_id)
    if purchase_service.supplier_in_use(db, supplier_id):
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{supplier.name}" tedarikcisinin satin alma kaydi var, silinemez. '
                'Bunun yerine pasife alin.'
            ),
        )
    try:
        db.delete(supplier)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    return None
