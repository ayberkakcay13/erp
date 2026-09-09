r"""Phase 14 migration: tedarikci ve satin alma.

Yaptiklari (hepsi IDEMPOTENT):
  1. Yeni tablolari olusturur (suppliers, purchase_orders, purchase_order_items,
     purchase_receipts, purchase_receipt_items, purchase_invoices,
     purchase_invoice_items)
  2. stock_ledger_entries tablosuna unit_cost kolonunu ekler
  3. Tablo daha once olustuysa create_all'in ekleyemedigi unique kisitlari
     tamamlar
  4. Her tenant icin `purchase` modulunu acar
  5. Yeni tablolarda tenant_id'yi NOT NULL yapar, RLS'i acar ve izolasyon
     politikasini kurar (Phase 12 kurali)

Kullanim (backend/ klasorunden):
    .\env\Scripts\python.exe migrate_phase14_purchase.py
"""
from sqlalchemy import inspect, text

from app import models  # noqa: F401  Base.metadata'yi doldurur
from app.database import Base, engine

NEW_TABLES = [
    'suppliers', 'purchase_orders', 'purchase_order_items',
    'purchase_receipts', 'purchase_receipt_items',
    'purchase_invoices', 'purchase_invoice_items',
]

LEDGER_COLUMNS = [
    ('unit_cost', 'NUMERIC(18, 4)'),
]

UNIQUE_CONSTRAINTS = [
    ('suppliers', 'uq_suppliers_tenant_code', 'tenant_id, code'),
    ('purchase_orders', 'uq_po_tenant_number', 'tenant_id, po_number'),
    ('purchase_receipts', 'uq_receipt_tenant_number', 'tenant_id, receipt_number'),
    ('purchase_invoices', 'uq_pinv_tenant_supplier_number',
     'tenant_id, supplier_id, invoice_number'),
    ('purchase_invoices', 'uq_pinv_tenant_internal', 'tenant_id, internal_number'),
]

POLICY_NAME = 'tenant_isolation'
POLICY_EXPRESSION = (
    "(current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int)"
)
APP_DB_ROLE = 'erp_app'


def column_exists(conn, table: str, column: str) -> bool:
    return conn.execute(
        text(
            'SELECT 1 FROM information_schema.columns '
            'WHERE table_name = :t AND column_name = :c'
        ),
        {'t': table, 'c': column},
    ).first() is not None


def constraint_exists(conn, name: str) -> bool:
    return conn.execute(
        text('SELECT 1 FROM pg_constraint WHERE conname = :n'), {'n': name}
    ).first() is not None


def step(n: int, title: str) -> None:
    print(f'\n[{n}] {title}')


def main() -> None:
    print('Phase 14 migration basliyor (idempotent).')

    step(1, 'Yeni tablolar olusturuluyor')
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    for name in NEW_TABLES:
        print(f'  [{"OK " if name in tables else "EKSIK"}] {name}')

    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))

        step(2, 'stock_ledger_entries birim maliyet kolonu')
        added = []
        for column, ddl in LEDGER_COLUMNS:
            if column_exists(conn, 'stock_ledger_entries', column):
                continue
            conn.execute(
                text(f'ALTER TABLE stock_ledger_entries ADD COLUMN {column} {ddl}')
            )
            added.append(column)
        print(f'  {"eklendi -> " + ", ".join(added) if added else "zaten var"}')

        step(3, 'Eksik unique kisitlari')
        added = []
        for table, name, columns in UNIQUE_CONSTRAINTS:
            if constraint_exists(conn, name):
                continue
            conn.execute(
                text(f'ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({columns})')
            )
            added.append(name)
        print(f'  {"eklendi -> " + ", ".join(added) if added else "zaten var"}')

        step(4, 'purchase modulu aciliyor')
        tenant_ids = [r[0] for r in conn.execute(text('SELECT id FROM tenants ORDER BY id'))]
        if not tenant_ids:
            print('  tenant yok - once Phase 12 migration calistirilmali')
        for tenant_id in tenant_ids:
            updated = conn.execute(
                text(
                    'UPDATE tenant_modules SET is_enabled = TRUE '
                    "WHERE tenant_id = :t AND module_code = 'purchase'"
                ),
                {'t': tenant_id},
            ).rowcount
            if not updated:
                conn.execute(
                    text(
                        'INSERT INTO tenant_modules '
                        '(tenant_id, module_code, is_enabled, created_at) '
                        "VALUES (:t, 'purchase', TRUE, NOW())"
                    ),
                    {'t': tenant_id},
                )
            print(f'  tenant {tenant_id}: purchase modulu acik')

        step(5, 'tenant_id NOT NULL + RLS')
        for table in NEW_TABLES:
            orphans = conn.execute(
                text(f'SELECT count(*) FROM {table} WHERE tenant_id IS NULL')
            ).scalar()
            if orphans:
                print(f'  {table}: {orphans} satirda tenant_id bos, NOT NULL atlandi')
            else:
                conn.execute(
                    text(f'ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL')
                )
            conn.execute(text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY'))
            conn.execute(text(f'DROP POLICY IF EXISTS {POLICY_NAME} ON {table}'))
            conn.execute(text(
                f'CREATE POLICY {POLICY_NAME} ON {table} '
                f'USING {POLICY_EXPRESSION} WITH CHECK {POLICY_EXPRESSION}'
            ))
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)'
            ))
            print(f'  {table}: RLS acik + FORCE + {POLICY_NAME}')

        conn.execute(text(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public '
            f'TO {APP_DB_ROLE}'
        ))
        conn.execute(text(
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_DB_ROLE}'
        ))
        print(f'  {APP_DB_ROLE} yetkileri tazelendi')

        step(6, 'Dogrulama')
        for table in NEW_TABLES:
            enabled, forced = conn.execute(
                text(
                    'SELECT c.relrowsecurity, c.relforcerowsecurity '
                    'FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
                    "WHERE c.relname = :t AND n.nspname = 'public'"
                ),
                {'t': table},
            ).first()
            print(f'  [{"OK " if enabled and forced else "EKSIK"}] {table}')

    print('\nMigration tamamlandi.')


if __name__ == '__main__':
    main()
