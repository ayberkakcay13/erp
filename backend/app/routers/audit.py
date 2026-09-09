"""Denetim izi okuma endpointleri (Phase 11). Sadece admin.

Log satirlari yalnizca okunur - degistirilemez, silinemez.
"""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import AuditLog, User
from ..schemas import AuditLogResponse

router = APIRouter(
    prefix='/api/audit-log',
    tags=['audit'],
    dependencies=[Depends(require_admin)],
)


def _serialize(log: AuditLog, emails: dict) -> dict:
    return {
        'id': log.id,
        'table_name': log.table_name,
        'record_id': log.record_id,
        'action': log.action,
        'field_name': log.field_name,
        'old_value': log.old_value,
        'new_value': log.new_value,
        'user_id': log.user_id,
        'user_email': emails.get(log.user_id),
        'ip_address': log.ip_address,
        'created_at': log.created_at,
    }


def _with_emails(db: Session, rows: list) -> list:
    """Kullanici e-postalarini tek sorguda cozer (N+1 olmasin)."""
    user_ids = {r.user_id for r in rows if r.user_id}
    emails = {}
    if user_ids:
        emails = {
            u.id: u.email
            for u in db.query(User).filter(User.id.in_(user_ids)).all()
        }
    return [_serialize(r, emails) for r in rows]


@router.get('', response_model=list[AuditLogResponse])
def list_audit_log(
    table: str | None = Query(None, description='Tablo adi'),
    record_id: int | None = Query(None),
    user_id: int | None = Query(None),
    action: str | None = Query(None, description='create/update/delete/submit/cancel'),
    date_from: date | None = Query(None, alias='from'),
    date_to: date | None = Query(None, alias='to'),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if table is not None:
        query = query.filter(AuditLog.table_name == table)
    if record_id is not None:
        query = query.filter(AuditLog.record_id == record_id)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if date_from is not None:
        query = query.filter(AuditLog.created_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        query = query.filter(AuditLog.created_at <= datetime.combine(date_to, time.max))

    rows = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return _with_emails(db, rows)


@router.get('/tables')
def audited_tables(db: Session = Depends(get_db)):
    """Log'da kaydi bulunan tablolar - filtre kutusunu doldurmak icin."""
    rows = db.query(AuditLog.table_name).distinct().order_by(AuditLog.table_name).all()
    return [r[0] for r in rows]


@router.get('/{table}/{record_id}', response_model=list[AuditLogResponse])
def record_history(
    table: str,
    record_id: int,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Tek bir kaydin degisiklik gecmisi - belge detayindaki sekme icin."""
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.table_name == table, AuditLog.record_id == record_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return _with_emails(db, rows)
