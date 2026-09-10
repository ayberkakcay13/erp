"""Belge numaralandirma servisi (Phase 11).

Numara ONAY (submit) aninda atanir - taslakta atanirsa silinen taslaklar
numara boslugu birakir ve bu yasal olarak sorun olur.

Artis ATOMIK'tir: `UPDATE ... SET current_number = current_number + 1
RETURNING current_number`. Python tarafinda okuyup +1 yapmak iki es zamanli
istekte ayni numarayi uretir.
"""
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

# doc_type -> (prefix, varsayilan padding)
DEFAULT_SERIES = {
    'invoice': ('FT', 5),          # fatura
    'sale': ('ST', 5),             # satis (eski, artik kullanilmiyor)
    'delivery_note': ('IR', 5),    # irsaliye
    'transfer': ('TR', 5),         # depo transferi
    'purchase_order': ('SAS', 5),    # satin alma siparisi
    'purchase_receipt': ('MK', 5),
    'purchase_invoice': ('AF', 5),
    'quotation': ('QT', 5),         # Phase 15: teklif
    'sales_order': ('SO', 5),       # Phase 15: satis siparisi
}


def ensure_series(
    db: Session, doc_type: str, year: Optional[int] = None, tenant_id: Optional[int] = None
) -> None:
    """Seri yoksa olusturur. Yil degisince yeni seri acilir (sayac sifirdan)."""
    if doc_type not in DEFAULT_SERIES:
        raise HTTPException(status_code=400, detail=f'Tanimsiz belge tipi: {doc_type}')
    prefix, padding = DEFAULT_SERIES[doc_type]
    target_year = year or date.today().year

    # WHERE NOT EXISTS: ayni seri iki kez acilmasin. Kismi unique index de
    # veritabani tarafinda ayni garantiyi verir (tenant_id NULL dahil).
    db.execute(
        text(
            'INSERT INTO naming_series '
            '(doc_type, prefix, year, current_number, padding, tenant_id, created_at) '
            'SELECT :doc_type, :prefix, :year, 0, :padding, :tenant_id, NOW() '
            'WHERE NOT EXISTS ('
            '  SELECT 1 FROM naming_series '
            '  WHERE doc_type = :doc_type AND year = :year '
            '    AND tenant_id IS NOT DISTINCT FROM :tenant_id'
            ')'
        ),
        {
            'doc_type': doc_type,
            'prefix': prefix,
            'year': target_year,
            'padding': padding,
            'tenant_id': tenant_id,
        },
    )


def _increment(db: Session, doc_type: str, year: int, tenant_id):
    """Sayaci tek SQL ifadesinde artirir. Seri yoksa None doner."""
    # Satir id uzerinden hedeflenir: WHERE kosuluyla dogrudan UPDATE etmek,
    # birden fazla satira denk geldiginde kilit sirasini degistirir ve
    # es zamanli isteklerde deadlock uretir.
    return db.execute(
        text(
            'UPDATE naming_series SET current_number = current_number + 1 '
            'WHERE id = ('
            '  SELECT id FROM naming_series '
            '  WHERE doc_type = :doc_type AND year = :year '
            '    AND tenant_id IS NOT DISTINCT FROM :tenant_id '
            '  ORDER BY id LIMIT 1'
            ') '
            'RETURNING prefix, year, current_number, padding'
        ),
        {'doc_type': doc_type, 'year': year, 'tenant_id': tenant_id},
    ).first()


def get_next_number(
    db: Session, doc_type: str, year: Optional[int] = None, tenant_id: Optional[int] = None
) -> str:
    """Sonraki belge numarasini uretir: `FT-2026-00001`.

    commit ETMEZ - cagiran belgeyle ayni transaction'da kalir. Boylece belge
    kaydedilemezse numara da tuketilmez.

    Once dogrudan UPDATE denenir; seri yoksa acilir ve tekrar denenir.
    `ensure_series`'i her cagrida calistirmak `ON CONFLICT`'in ayni satirda
    ek kilit almasina ve es zamanli isteklerde deadlock'a yol aciyordu.
    """
    target_year = year or date.today().year

    row = _increment(db, doc_type, target_year, tenant_id)
    if row is None:
        ensure_series(db, doc_type, target_year, tenant_id)
        row = _increment(db, doc_type, target_year, tenant_id)

    if row is None:
        raise HTTPException(
            status_code=500, detail=f'"{doc_type}" icin numaralandirma serisi bulunamadi'
        )

    prefix, series_year, number, padding = row
    return f'{prefix}-{series_year}-{number:0{padding}d}'
