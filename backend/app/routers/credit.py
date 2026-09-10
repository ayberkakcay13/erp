"""Musteri kredi limiti endpointleri (Phase 15)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import Customer, User
from ..schemas import CreditCheckResponse, CustomerCreditSummary, CustomerCreditUpdate
from ..services import credit_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/credit',
    tags=['credit'],
    dependencies=[Depends(get_current_user), Depends(require_module('sales'))],
)


@router.get('/customers', response_model=list[CustomerCreditSummary])
def list_customer_credit(db: Session = Depends(get_db)):
    return credit_service.all_summaries(db)


@router.get('/customers/{customer_id}', response_model=CustomerCreditSummary)
def get_customer_credit(customer_id: int, db: Session = Depends(get_db)):
    return credit_service.customer_summary(db, customer_id)


@router.get('/customers/{customer_id}/check', response_model=CreditCheckResponse)
def check_customer_credit(
    customer_id: int,
    amount: str = '0',
    db: Session = Depends(get_db),
):
    return credit_service.check_credit(db, customer_id, amount)


@router.put('/customers/{customer_id}', response_model=CustomerCreditSummary)
def update_customer_credit(
    customer_id: int,
    payload: CustomerCreditUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f'Musteri {customer_id} bulunamadi')
    customer.credit_limit = payload.credit_limit
    customer.credit_days = payload.credit_days
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Kredi limiti guncellenemedi: {exc}')
    return credit_service.customer_summary(db, customer_id)
