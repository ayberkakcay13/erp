"""Numaralandirma serisi yonetimi (Phase 11). Sadece admin."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import NamingSeries, User
from ..schemas import NamingSeriesResponse, NamingSeriesUpdate
from ..services.naming_service import DEFAULT_SERIES

router = APIRouter(
    prefix='/api/naming-series',
    tags=['naming-series'],
    dependencies=[Depends(require_admin)],
)


def _serialize(series: NamingSeries) -> dict:
    """Siradaki numarayi da gosterir - sayac tuketilmeden onizleme."""
    return {
        'id': series.id,
        'doc_type': series.doc_type,
        'prefix': series.prefix,
        'year': series.year,
        'current_number': series.current_number,
        'padding': series.padding,
        'tenant_id': series.tenant_id,
        'next_number': (
            f'{series.prefix}-{series.year}-'
            f'{series.current_number + 1:0{series.padding}d}'
        ),
        'created_at': series.created_at,
    }


@router.get('', response_model=list[NamingSeriesResponse])
def list_series(
    year: int | None = Query(None, description='Yila gore filtrele'),
    db: Session = Depends(get_db),
):
    query = db.query(NamingSeries)
    if year is not None:
        query = query.filter(NamingSeries.year == year)
    rows = query.order_by(NamingSeries.year.desc(), NamingSeries.doc_type).all()
    return [_serialize(s) for s in rows]


@router.get('/doc-types')
def list_doc_types():
    """Tanimli belge tipleri ve varsayilan onekleri."""
    return [
        {'doc_type': doc_type, 'prefix': prefix, 'padding': padding}
        for doc_type, (prefix, padding) in DEFAULT_SERIES.items()
    ]


@router.put('/{series_id}', response_model=NamingSeriesResponse)
def update_series(
    series_id: int,
    payload: NamingSeriesUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Seriyi gunceller.

    `current_number` GERIYE alinamaz: daha once kullanilmis numaralar tekrar
    uretilir ve seride cakisma olusur.
    """
    series = db.get(NamingSeries, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail=f'Seri {series_id} bulunamadi')

    data = payload.model_dump(exclude_unset=True)
    new_number = data.get('current_number')
    if new_number is not None and new_number < series.current_number:
        raise HTTPException(
            status_code=400,
            detail=(
                f'Sayac geriye alinamaz ({series.current_number} -> {new_number}): '
                'kullanilmis numaralar tekrar uretilir.'
            ),
        )

    for field, value in data.items():
        setattr(series, field, value)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Seri guncellenemedi: {exc}')
    db.refresh(series)
    return _serialize(series)


@router.get('/current-year')
def current_year_summary(db: Session = Depends(get_db)):
    """Bu yilin serileri; eksik olanlar 'tanimsiz' olarak isaretlenir."""
    year = date.today().year
    existing = {
        s.doc_type: s
        for s in db.query(NamingSeries).filter(NamingSeries.year == year).all()
    }
    return {
        'year': year,
        'series': [
            _serialize(existing[doc_type]) if doc_type in existing
            else {
                'doc_type': doc_type,
                'prefix': prefix,
                'year': year,
                'current_number': 0,
                'padding': padding,
                'next_number': f'{prefix}-{year}-{1:0{padding}d}',
                'defined': False,
            }
            for doc_type, (prefix, padding) in DEFAULT_SERIES.items()
        ],
    }
