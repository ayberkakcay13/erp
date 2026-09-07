r"""Phase 11 migration: belge durumu, numaralandirma serileri, denetim izi.

Yaptiklari (hepsi IDEMPOTENT):
  1. Yeni tablolari olusturur (naming_series, audit_logs)
  2. sales / invoices / stock_transfers tablolarina docstatus + yasam dongusu
     kolonlarini ekler
  3. Mevcut kayitlari isaretler: iptal olanlar docstatus=2, digerleri 1
  4. invoices.invoice_number ve stock_transfers.transfer_no NULL kabul eder
     (taslak belgede numara olmaz)
  5. Bu yil icin varsayilan numaralandirma serilerini acar; mevcut FT-YYYY-*
     numaralari varsa sayaci en yuksek numaradan devam ettirir

Eski fatura numaralari (INV-<sale>-<timestamp>) OLDUGU GIBI KORUNUR; yeni
faturalar FT-2026-00001 formatinda numaralanir.

Kullanim (backend/ klasorunden):
    .\env\Scripts\python.exe migrate_phase11_documents.py
"""
import re
from datetime import date

from sqlalchemy import inspect, text

from app.database import Base, engine
from app.services.naming_service import DEFAULT_SERIES

# tablo -> mevcut kayitlari iptal sayan kosul (digerleri onayli kabul edilir)
DOCUMENT_TABLES = {
    'sales': "status = 'cancelled'",
    'invoices': "status = 'cancelled'",
    'stock_transfers': "status = 'cancelled'",
}

LIFECYCLE_COLUMNS = [
    ('docstatus', 'INTEGER NOT NULL DEFAULT 0'),
    ('submitted_at', 'TIMESTAMP'),
    ('submitted_by', 'INTEGER REFERENCES users(id)'),
    ('cancelled_at', 'TIMESTAMP'),
    ('cancelled_by', 'INTEGER REFERENCES users(id)'),
    ('cancel_reason', 'TEXT'),
]


def column_exists(conn, table: str, column: str) -> bool:
    return conn.execute(
        text(
            'SELECT 1 FROM information_schema.columns '
            'WHERE table_name = :t AND column_name = :c'
        ),
        {'t': table, 'c': column},
    ).first() is not None


def step(n: int, title: str) -> None:
    print(f'\n[{n}] {title}')


def main() -> None:
    print('Phase 11 migration basliyor (idempotent).')

    step(1, 'Yeni tablolar olusturuluyor')
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    for name in ('naming_series', 'audit_logs'):
        print(f'  [{"OK " if name in tables else "EKSIK"}] {name}')

    with engine.begin() as conn:
        step(2, 'Belge yasam dongusu kolonlari')
        for table in DOCUMENT_TABLES:
            added = []
            for column, ddl in LIFECYCLE_COLUMNS:
                if column_exists(conn, table, column):
                    continue
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
                added.append(column)
            print(f'  {table}: {"eklendi -> " + ", ".join(added) if added else "zaten var"}')

        step(3, 'Mevcut kayitlarin docstatus degeri')
        for table, cancelled_condition in DOCUMENT_TABLES.items():
            # Sadece hic dokunulmamis (docstatus=0) kayitlar isaretlenir;
            # tekrar calistirmada onceki islem bozulmaz.
            cancelled = conn.execute(text(
                f'UPDATE {table} SET docstatus = 2 '
                f'WHERE docstatus = 0 AND {cancelled_condition}'
            )).rowcount
            submitted = conn.execute(text(
                f'UPDATE {table} SET docstatus = 1 '
                f'WHERE docstatus = 0 AND NOT ({cancelled_condition})'
            )).rowcount
            print(f'  {table}: {submitted} onayli, {cancelled} iptal olarak isaretlendi')

        step(4, 'Numara kolonlari NULL kabul etsin (taslak belge numara almaz)')
        for table, column in (('invoices', 'invoice_number'),
                              ('stock_transfers', 'transfer_no')):
            nullable = conn.execute(
                text(
                    'SELECT is_nullable FROM information_schema.columns '
                    'WHERE table_name = :t AND column_name = :c'
                ),
                {'t': table, 'c': column},
            ).scalar()
            if nullable == 'YES':
                print(f'  {table}.{column}: zaten nullable')
            else:
                conn.execute(text(
                    f'ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL'
                ))
                print(f'  {table}.{column}: NOT NULL kaldirildi')

        step(5, 'Mukerrer numaralandirma serileri temizleniyor')
        # UNIQUE(doc_type, year, tenant_id) kisiti tenant_id NULL iken
        # mukerrer satira izin veriyordu; en yuksek sayacli satir korunur.
        removed = conn.execute(text(
            'DELETE FROM naming_series ns WHERE EXISTS ('
            '  SELECT 1 FROM naming_series other '
            '  WHERE other.doc_type = ns.doc_type AND other.year = ns.year '
            '    AND other.tenant_id IS NOT DISTINCT FROM ns.tenant_id '
            '    AND (other.current_number, other.id) > (ns.current_number, ns.id)'
            ')'
        )).rowcount
        print(f'  {removed} mukerrer satir silindi')

        conn.execute(text('ALTER TABLE naming_series DROP CONSTRAINT IF EXISTS '
                          'uq_naming_series_type_year'))
        conn.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_naming_series_global '
            'ON naming_series (doc_type, year) WHERE tenant_id IS NULL'
        ))
        conn.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_naming_series_tenant '
            'ON naming_series (doc_type, year, tenant_id) WHERE tenant_id IS NOT NULL'
        ))
        print('  kismi unique indexler hazir')

        step(6, 'Varsayilan numaralandirma serileri')
        year = date.today().year
        for doc_type, (prefix, padding) in DEFAULT_SERIES.items():
            existing = conn.execute(
                text(
                    'SELECT id, current_number FROM naming_series '
                    'WHERE doc_type = :d AND year = :y AND tenant_id IS NULL'
                ),
                {'d': doc_type, 'y': year},
            ).first()
            if existing:
                print(f'  {doc_type} ({prefix}-{year}): zaten var, sayac={existing[1]}')
                continue

            # Bu onekte kayitli numara varsa sayaci en yuksekten devam ettir
            start = 0
            if doc_type == 'invoice':
                start = _max_existing(conn, 'invoices', 'invoice_number', prefix, year)
            elif doc_type == 'transfer':
                start = _max_existing(conn, 'stock_transfers', 'transfer_no', prefix, year)

            conn.execute(
                text(
                    'INSERT INTO naming_series '
                    '(doc_type, prefix, year, current_number, padding, tenant_id, created_at) '
                    'VALUES (:d, :p, :y, :n, :pad, NULL, NOW())'
                ),
                {'d': doc_type, 'p': prefix, 'y': year, 'n': start, 'pad': padding},
            )
            print(f'  {doc_type} ({prefix}-{year}): olusturuldu, sayac={start}')

    print('\nMigration tamamlandi.')


def _max_existing(conn, table: str, column: str, prefix: str, year: int) -> int:
    """`PREFIX-YIL-NNNNN` bicimindeki mevcut numaralarin en buyugunu bulur."""
    pattern = f'{prefix}-{year}-%'
    rows = conn.execute(
        text(f'SELECT {column} FROM {table} WHERE {column} LIKE :p'), {'p': pattern}
    ).all()
    highest = 0
    for (value,) in rows:
        match = re.fullmatch(rf'{re.escape(prefix)}-{year}-(\d+)', value or '')
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


if __name__ == '__main__':
    main()
