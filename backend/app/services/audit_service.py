"""Denetim izi (audit trail) ve belge degismezligi (Phase 11).

Iki kural tek yerde, SQLAlchemy `before_flush` dinleyicisiyle uygulanir -
boylece her router'da tekrar yazilmasi gerekmez:

1. **Degismezlik:** `docstatus = 1 (onayli)` veya `2 (iptal)` olan bir belge
   degistirilemez / silinemez. Yalnizca submit/cancel akisinin dokundugu
   yasam dongusu alanlari degisebilir.
2. **Denetim izi:** gercekten degisen her alan icin bir `audit_logs` satiri
   yazilir. Hassas alanlar (sifre, token) loglanmaz.

Istek sahibini bilmek icin `contextvars` kullaniliyor; middleware her istekte
kullanici ve IP bilgisini buraya koyar.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from ..models import (
    DOC_LIFECYCLE_FIELDS,
    DOCUMENT_MODELS,
    AuditLog,
    DocStatus,
    DocumentImmutableError,
)

# Istek basina kullanici / IP baglami
current_user_id: ContextVar[int | None] = ContextVar('current_user_id', default=None)
current_ip: ContextVar[str | None] = ContextVar('current_ip', default=None)

# submit/cancel akisi degismezlik kontrolunu bilerek atlar
_lifecycle_write: ContextVar[bool] = ContextVar('_lifecycle_write', default=False)

# Denetim izine girmeyen tablolar: log'un kendisi, defter (zaten degismez ve
# cok satirli), oturum/teknik tablolar
SKIPPED_TABLES = {'audit_logs', 'stock_ledger_entries'}

# Asla loglanmayacak alanlar
SENSITIVE_FIELDS = {
    'password', 'hashed_password', 'access_token', 'refresh_token',
    'token', 'secret', 'secret_key', 'api_key',
}


@contextmanager
def lifecycle_write():
    """submit/cancel sirasinda degismezlik kontrolunu gecici olarak devre disi birakir."""
    token = _lifecycle_write.set(True)
    try:
        yield
    finally:
        _lifecycle_write.reset(token)


def _stringify(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    text_value = str(value)
    # Cok uzun degerler log tablosunu sisirmesin
    return text_value if len(text_value) <= 1000 else text_value[:997] + '...'


def _changed_fields(obj) -> dict:
    """Bu flush'ta gercekten degisen alanlar: {alan: (eski, yeni)}."""
    state = inspect(obj)
    changes = {}
    for attr in state.mapper.column_attrs:
        history = state.attrs[attr.key].history
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        if old == new:
            continue  # deger ayni - satir atma
        changes[attr.key] = (old, new)
    return changes


def _check_document_immutability(obj, changes: dict) -> None:
    """Onayli/iptal belgede is alanlarinin degismesini engeller."""
    if type(obj).__name__ not in DOCUMENT_MODELS:
        return
    if _lifecycle_write.get():
        return

    state = inspect(obj)
    history = state.attrs['docstatus'].history
    # Veritabanindaki (degisiklikten onceki) docstatus
    previous = history.deleted[0] if history.deleted else obj.docstatus
    if previous == DocStatus.DRAFT:
        return

    business_changes = set(changes) - DOC_LIFECYCLE_FIELDS
    if not business_changes:
        return

    label = DocStatus.LABELS.get(previous, previous)
    raise DocumentImmutableError(
        f'{label.capitalize()} belge degistirilemez '
        f'(degistirilmeye calisilan alanlar: {", ".join(sorted(business_changes))}). '
        'Duzeltme icin belgeyi iptal edip yenisini olusturun.'
    )


def _check_document_deletable(obj) -> None:
    if type(obj).__name__ not in DOCUMENT_MODELS:
        return
    if obj.docstatus != DocStatus.DRAFT:
        label = DocStatus.LABELS.get(obj.docstatus, obj.docstatus)
        raise DocumentImmutableError(
            f'{label.capitalize()} belge silinemez. Yalnizca taslak belgeler silinebilir.'
        )


def _row(obj, action: str, field=None, old=None, new=None) -> dict:
    from . import tenant_context  # gec import: dairesel bagimliligi kirar

    # Log satirlari Core INSERT ile yaziliyor; ORM'in tenant damgalamasi
    # buraya ulasmaz, tenant_id acikca doldurulur (audit_logs RLS altinda).
    tenant_id = getattr(obj, 'tenant_id', None) or tenant_context.current_tenant_id.get()
    return {
        'tenant_id': tenant_id,
        'table_name': obj.__tablename__,
        'record_id': getattr(obj, 'id', None),
        'action': action,
        'field_name': field,
        'old_value': _stringify(old),
        'new_value': _stringify(new),
        'user_id': current_user_id.get(),
        'ip_address': current_ip.get(),
        'created_at': datetime.utcnow(),
    }


def _buffer(session: Session) -> dict:
    """Bu flush'ta yazilacak log satirlari, session'a asili gecici tampon."""
    return session.info.setdefault('_audit', {'rows': [], 'created': []})


def _lifecycle_action(changes: dict) -> str | None:
    """docstatus gecisini submit/cancel olarak etiketler."""
    if 'docstatus' not in changes:
        return None
    _, new = changes['docstatus']
    if new == DocStatus.SUBMITTED:
        return 'submit'
    if new == DocStatus.CANCELLED:
        return 'cancel'
    return None


def before_flush(session: Session, flush_context, instances):  # noqa: ARG001
    """Degismezligi dogrular ve denetim izi satirlarini tamponlar."""
    buffer = _buffer(session)

    for obj in list(session.dirty):
        if isinstance(obj, AuditLog) or obj.__tablename__ in SKIPPED_TABLES:
            continue
        if not session.is_modified(obj, include_collections=False):
            continue
        changes = _changed_fields(obj)
        if not changes:
            continue
        _check_document_immutability(obj, changes)

        action = _lifecycle_action(changes) or 'update'
        for field, (old, new) in changes.items():
            if field in SENSITIVE_FIELDS:
                continue
            buffer['rows'].append(_row(obj, action, field, old, new))

    for obj in list(session.deleted):
        if isinstance(obj, AuditLog):
            continue
        _check_document_deletable(obj)
        if obj.__tablename__ not in SKIPPED_TABLES:
            buffer['rows'].append(_row(obj, 'delete'))

    for obj in list(session.new):
        if isinstance(obj, AuditLog) or obj.__tablename__ in SKIPPED_TABLES:
            continue
        # id henuz yok; after_flush'ta doldurulur
        buffer['created'].append(obj)


def after_flush(session: Session, flush_context):  # noqa: ARG001
    """Tamponlanan satirlari yazar.

    ORM nesnesi eklemek yerine dogrudan INSERT calistiriliyor: after_flush
    icinde eklenen nesneler bu flush'a dahil edilmez.
    """
    buffer = session.info.get('_audit')
    if not buffer:
        return
    rows = buffer['rows']
    for obj in buffer['created']:
        rows.append(_row(obj, 'create'))
    buffer['rows'] = []
    buffer['created'] = []
    if rows:
        session.execute(AuditLog.__table__.insert(), rows)


def register(session_factory) -> None:
    """Dinleyicileri uygulamanin session factory'sine baglar."""
    event.listen(session_factory, 'before_flush', before_flush)
    event.listen(session_factory, 'after_flush', after_flush)
