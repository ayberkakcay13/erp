"""Musteri kredi limiti servisi (Phase 15).

Kredi kullanimi TEK KAYNAKTAN hesaplanir: onayli (docstatus=1), henuz tam
odenmemis faturalarin toplami. Ayri bir `credit_used` kolonu tutulmaz -
senkron kalmasi gereken bir denormalizasyon eklemek yerine her seferinde
faturalardan hesaplanir.

Kredi limiti VARSAYILAN OLARAK UYARIR, ENGELLEMEZ: `check_credit()` her
zaman bir sonuc doner; `block_if_exceeded=True` verilirse asim durumunda
400 firlatir. `credit_limit == 0` limitsiz musteri anlamina gelir.
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Customer, Invoice

ZERO = Decimal('0')


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f'Musteri {customer_id} bulunamadi')
    return customer


def credit_used(db: Session, customer_id: int) -> Decimal:
    """Onayli, henuz tam odenmemis faturalarin toplami."""
    rows = (
        db.query(Invoice.total_amount)
        .filter(
            Invoice.customer_id == customer_id,
            Invoice.docstatus == 1,
            Invoice.payment_status != 'odendi',
        )
        .all()
    )
    return sum((to_decimal(r[0]) for r in rows), ZERO)


def check_credit(
    db: Session,
    customer_id: int,
    additional_amount,
    block_if_exceeded: bool = False,
) -> dict:
    """Kredi limiti kontrolu. Limit 0 ise her zaman izin verir (limitsiz)."""
    customer = get_customer(db, customer_id)
    limit = to_decimal(customer.credit_limit or 0)
    used = credit_used(db, customer_id)
    requested = to_decimal(additional_amount)
    available = limit - used

    if limit == ZERO:
        return {
            'allowed': True,
            'credit_limit': limit,
            'credit_used': used,
            'available': None,
            'requested': requested,
            'message': None,
        }

    allowed = (used + requested) <= limit
    message = None
    if not allowed:
        message = (
            f'"{customer.name}" icin kredi limiti asiliyor: '
            f'kullanilan {used} + istenen {requested} > limit {limit}'
        )
        if block_if_exceeded:
            raise HTTPException(status_code=400, detail=message)

    return {
        'allowed': allowed,
        'credit_limit': limit,
        'credit_used': used,
        'available': available,
        'requested': requested,
        'message': message,
    }


def customer_summary(db: Session, customer_id: int) -> dict:
    customer = get_customer(db, customer_id)
    limit = to_decimal(customer.credit_limit or 0)
    used = credit_used(db, customer_id)
    return {
        'customer_id': customer.id,
        'customer_name': customer.name,
        'credit_limit': limit,
        'credit_used': used,
        'available': (limit - used) if limit > ZERO else None,
        'credit_days': customer.credit_days or 0,
    }


def all_summaries(db: Session) -> list:
    return [customer_summary(db, c.id) for c in db.query(Customer).order_by(Customer.name).all()]
