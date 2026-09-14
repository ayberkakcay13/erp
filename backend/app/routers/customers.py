"""Customer CRUD endpointleri."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import Customer, User
from ..schemas import CustomerCreate, CustomerResponse, CustomerUpdate
from ..services import sales_query_service

router = APIRouter(
    prefix='/api/customers',
    tags=['customers'],
    dependencies=[Depends(get_current_user)],
)


def _get_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f'Customer {customer_id} bulunamadi')
    return customer


@router.post('', response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    customer = Customer(**payload.model_dump())
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'"{payload.email}" e-postasi zaten kayitli')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(customer)
    return customer


@router.get('', response_model=list[CustomerResponse])
def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.query(Customer).order_by(Customer.id).offset(skip).limit(limit).all()


@router.get('/{customer_id}', response_model=CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, customer_id)


@router.put('/{customer_id}', response_model=CustomerResponse)
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)):
    customer = _get_or_404(db, customer_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu e-posta baska bir musteride kayitli')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(customer)
    return customer


@router.delete('/{customer_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),  # silme sadece admin
):
    customer = _get_or_404(db, customer_id)
    try:
        db.delete(customer)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    return None


# --- Phase 19: musteri detay modal'i (gercek sales_orders sorgusu) ---

@router.get('/{customer_id}/orders')
def get_customer_orders(
    customer_id: int,
    status: str | None = Query(None, description='pending | processing | delivered'),
    db: Session = Depends(get_db),
):
    """Musteriye ait siparisler (CustomerDetailModal - Devam Eden/Son Siparisler sekmeleri)."""
    return sales_query_service.get_customer_orders(db, customer_id, status)


@router.get('/{customer_id}/sales-trend')
def get_customer_sales_trend(
    customer_id: int,
    range: str = Query('monthly', alias='range', description='daily | weekly | monthly | yearly'),
    date: str | None = Query(None, description='ISO tarih, secili donemi belirler'),
    db: Session = Depends(get_db),
):
    """Musteri bazli satis trendi (CustomerDetailModal - Satis Trendi sekmesi)."""
    target = sales_query_service.parse_date(date)
    return sales_query_service.get_sales_trend(db, range, target, customer_id=customer_id)
