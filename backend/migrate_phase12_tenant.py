r"""Phase 12 migration: cok kiracili mimari + PostgreSQL Row Level Security.

Yaptiklari (hepsi IDEMPOTENT):
  1. tenants / tenant_modules tablolarini olusturur
  2. Tum is tablolarina `tenant_id` kolonu + index ekler
  3. users.is_superadmin kolonunu ekler
  4. Varsayilan tenant'i acar ve mevcut TUM veriyi ona tasir
  5. tenant_id'yi NOT NULL yapar (users haric - superadmin tenant'siz olabilir)
  6. Global unique kisitlari TENANT BAZLI olanlarla degistirir
     (sku, musteri e-postasi, depo kodu, fatura no, transfer no)
  7. Her tenant'li tabloda RLS'i acar, FORCE eder ve izolasyon politikasi kurar

RLS notu: politikalar `app.current_tenant_id` ve `app.bypass_rls` oturum
degiskenlerini okur. Uygulama bunlari her transaction basinda `SET LOCAL`
ile yazar (app/services/tenant_context.py).

FORCE ROW LEVEL SECURITY kritik: RLS varsayilan olarak TABLO SAHIBINI atlar.

Bundan da onemlisi: Supabase'in `postgres` rolu **BYPASSRLS** ayricaligina
sahip. Bu ayricalik RLS'i butunuyle devre disi birakir - ENABLE ve FORCE bile
bir sey degistirmez. Cozum, ayricaligi olmayan bir `erp_app` rolu acmak ve
uygulamanin her transaction'da `SET LOCAL ROLE erp_app` ile ona gecmesi
(app/services/tenant_context.py). Baglanti bilgileri degismedigi icin .env'e
dokunmak gerekmez; rol degisimi transaction'a bagli oldugu icin de Supabase
Transaction Pooler uzerinden sizmaz.

Kullanim (backend/ klasorunden):
    .\env\Scripts\python.exe migrate_phase12_tenant.py
"""
from sqlalchemy import inspect, text

from app.database import Base, engine
from app.models import MODULE_CODES

DEFAULT_TENANT_SLUG = 'varsayilan'
DEFAULT_TENANT_NAME = 'Varsayilan Firma'

# tenant_id tasiyacak tablolar
TENANT_TABLES = [
    'customers', 'products', 'sales', 'sales_items', 'invoices',
    'warehouses', 'stock_ledger_entries', 'stock_transfers',
    'stock_transfer_items', 'naming_series', 'audit_logs', 'users',
]

# tenant_id NOT NULL yapilmayacaklar: superadmin hicbir firmaya bagli degildir
NULLABLE_TENANT_TABLES = {'users'}

# (tablo, eski global kisit adi, yeni kisit adi, kolonlar)
UNIQUE_MIGRATIONS = [
    ('products', 'products_sku_key', 'uq_products_tenant_sku', 'tenant_id, sku'),
    ('customers', 'customers_email_key', 'uq_customers_tenant_email', 'tenant_id, email'),
    ('warehouses', 'warehouses_code_key', 'uq_warehouses_tenant_code', 'tenant_id, code'),
    ('invoices', 'invoices_invoice_number_key', 'uq_invoices_tenant_number',
     'tenant_id, invoice_number'),
    ('stock_transfers', 'stock_transfers_transfer_no_key', 'uq_transfers_tenant_number',
     'tenant_id, transfer_no'),
]

POLICY_NAME = 'tenant_isolation'

# Uygulamanin RLS'e tabi olarak calistigi rol
APP_DB_ROLE = 'erp_app'

# Politika hem okuma (USING) hem yazma (WITH CHECK) icin ayni kurali uygular.
# NULLIF: uygulama tenant yokken bos string yaziyor, onu NULL'a cevirir -
# NULL karsilastirmasi false doner, yani "tenant yoksa hicbir satir".
POLICY_EXPRESSION = (
    "(current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int)"
)


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
    print('Phase 12 migration basliyor (idempotent).')

    step(1, 'tenants / tenant_modules tablolari')
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    for name in ('tenants', 'tenant_modules'):
        print(f'  [{"OK " if name in tables else "EKSIK"}] {name}')

    with engine.begin() as conn:
        # Migration kendi yazdigi RLS politikalarina takilmasin
        # 3. parametre true = SET LOCAL: ayar transaction ile sinirli kalir.
        # false (oturum duzeyi) verilirse Supabase Transaction Pooler
        # baglantiyi havuza geri verdiginde muafiyet sonraki kiraciya sizar.
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))

        step(2, 'tenant_id kolonlari')
        for table in TENANT_TABLES:
            if column_exists(conn, table, 'tenant_id'):
                print(f'  {table}: zaten var')
                continue
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN tenant_id INTEGER'))
            conn.execute(text(
                f'ALTER TABLE {table} ADD CONSTRAINT {table}_tenant_id_fkey '
                'FOREIGN KEY (tenant_id) REFERENCES tenants(id)'
            ))
            print(f'  {table}: eklendi')
        for table in TENANT_TABLES:
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id '
                f'ON {table} (tenant_id)'
            ))
        print('  indexler hazir')

        step(3, 'users.is_superadmin kolonu')
        if column_exists(conn, 'users', 'is_superadmin'):
            print('  zaten var')
        else:
            conn.execute(text(
                'ALTER TABLE users ADD COLUMN is_superadmin BOOLEAN NOT NULL DEFAULT FALSE'
            ))
            print('  eklendi')

        step(4, 'Varsayilan tenant ve mevcut verinin tasinmasi')
        row = conn.execute(
            text('SELECT id FROM tenants WHERE slug = :s'), {'s': DEFAULT_TENANT_SLUG}
        ).first()
        if row:
            tenant_id = row[0]
            print(f'  "{DEFAULT_TENANT_NAME}" zaten var (id={tenant_id})')
        else:
            tenant_id = conn.execute(
                text(
                    'INSERT INTO tenants (name, slug, is_active, plan, created_at) '
                    "VALUES (:n, :s, TRUE, 'pro', NOW()) RETURNING id"
                ),
                {'n': DEFAULT_TENANT_NAME, 's': DEFAULT_TENANT_SLUG},
            ).scalar()
            print(f'  "{DEFAULT_TENANT_NAME}" olusturuldu (id={tenant_id})')

        # Varsayilan tenant'ta tum moduller acik
        for code in MODULE_CODES:
            conn.execute(
                text(
                    'INSERT INTO tenant_modules (tenant_id, module_code, is_enabled) '
                    'SELECT :t, :c, TRUE WHERE NOT EXISTS ('
                    '  SELECT 1 FROM tenant_modules '
                    '  WHERE tenant_id = :t AND module_code = :c)'
                ),
                {'t': tenant_id, 'c': code},
            )

        moved = 0
        for table in TENANT_TABLES:
            moved += conn.execute(
                text(f'UPDATE {table} SET tenant_id = :t WHERE tenant_id IS NULL'),
                {'t': tenant_id},
            ).rowcount
        print(f'  {moved} satir varsayilan tenant\'a tasindi')

        # Ilk kullanici platform sahibi olsun (tenant'lar ustu yonetim)
        promoted = conn.execute(text(
            'UPDATE users SET is_superadmin = TRUE WHERE id = ('
            '  SELECT id FROM users ORDER BY id LIMIT 1'
            ') AND is_superadmin = FALSE'
        )).rowcount
        print(f'  {promoted} kullanici platform sahibi olarak isaretlendi')

        step(5, 'tenant_id NOT NULL')
        for table in TENANT_TABLES:
            if table in NULLABLE_TENANT_TABLES:
                print(f'  {table}: bilerek nullable (superadmin tenant\'siz olabilir)')
                continue
            nullable = conn.execute(
                text(
                    'SELECT is_nullable FROM information_schema.columns '
                    'WHERE table_name = :t AND column_name = :c'
                ),
                {'t': table, 'c': 'tenant_id'},
            ).scalar()
            if nullable == 'NO':
                print(f'  {table}: zaten NOT NULL')
                continue
            orphans = conn.execute(
                text(f'SELECT count(*) FROM {table} WHERE tenant_id IS NULL')
            ).scalar()
            if orphans:
                print(f'  {table}: ATLANDI - {orphans} satirda tenant_id bos')
                continue
            conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL'))
            print(f'  {table}: NOT NULL')

        step(6, 'Unique kisitlari tenant bazli')
        for table, old_name, new_name, columns in UNIQUE_MIGRATIONS:
            conn.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {old_name}'))
            if constraint_exists(conn, new_name):
                print(f'  {table}: {new_name} zaten var')
                continue
            conn.execute(text(
                f'ALTER TABLE {table} ADD CONSTRAINT {new_name} UNIQUE ({columns})'
            ))
            print(f'  {table}: UNIQUE({columns})')

        # naming_series: kismi indexler tenant_id NULL/NOT NULL ayrimini zaten yapiyor
        step(7, 'Ayricaliksiz uygulama rolu (erp_app)')
        # RLS'e TABI bir rol: NOBYPASSRLS + NOSUPERUSER. Giris bilgileri
        # degismiyor; uygulama postgres ile baglanip transaction basinda
        # `SET LOCAL ROLE erp_app` yapiyor.
        conn.execute(text(
            "DO $$ BEGIN "
            f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_DB_ROLE}') "
            f"  THEN CREATE ROLE {APP_DB_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS; "
            "  END IF; "
            "END $$;"
        ))
        # Uygulama rolune gecebilmek icin uyelik gerekiyor
        conn.execute(text(f'GRANT {APP_DB_ROLE} TO CURRENT_USER'))
        conn.execute(text(f'GRANT USAGE ON SCHEMA public TO {APP_DB_ROLE}'))
        conn.execute(text(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public '
            f'TO {APP_DB_ROLE}'
        ))
        conn.execute(text(
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_DB_ROLE}'
        ))
        # Sonradan eklenen tablolar da otomatik yetkili olsun
        conn.execute(text(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_DB_ROLE}'
        ))
        conn.execute(text(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'GRANT USAGE, SELECT ON SEQUENCES TO {APP_DB_ROLE}'
        ))
        bypasses = conn.execute(
            text('SELECT rolbypassrls FROM pg_roles WHERE rolname = :r'),
            {'r': APP_DB_ROLE},
        ).scalar()
        print(f'  {APP_DB_ROLE} hazir (bypassrls={bypasses})')

        step(8, 'Row Level Security politikalari')
        for table in TENANT_TABLES:
            conn.execute(text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
            # FORCE olmadan politikalar tablo sahibi icin (uygulamanin baglandigi
            # postgres rolu) hic calismazdi.
            conn.execute(text(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY'))
            conn.execute(text(f'DROP POLICY IF EXISTS {POLICY_NAME} ON {table}'))
            conn.execute(text(
                f'CREATE POLICY {POLICY_NAME} ON {table} '
                f'USING {POLICY_EXPRESSION} WITH CHECK {POLICY_EXPRESSION}'
            ))
            print(f'  {table}: RLS acik + FORCE + {POLICY_NAME}')

        step(9, 'Dogrulama')
        for table in TENANT_TABLES:
            # Sema filtresi sart: Supabase'de ayrica bir `auth.users` tablosu
            # var, filtresiz sorgu yanlis satiri getiriyor.
            enabled, forced = conn.execute(
                text(
                    'SELECT c.relrowsecurity, c.relforcerowsecurity '
                    'FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
                    "WHERE c.relname = :t AND n.nspname = 'public'"
                ),
                {'t': table},
            ).first()
            policies = conn.execute(
                text(
                    'SELECT count(*) FROM pg_policies '
                    "WHERE tablename = :t AND schemaname = 'public'"
                ),
                {'t': table},
            ).scalar()
            mark = 'OK ' if (enabled and forced and policies) else 'EKSIK'
            print(f'  [{mark}] {table}: rls={enabled} force={forced} politika={policies}')

        app_bypass = conn.execute(
            text('SELECT rolbypassrls FROM pg_roles WHERE rolname = :r'),
            {'r': APP_DB_ROLE},
        ).scalar()
        connect_bypass = conn.execute(
            text('SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user')
        ).scalar()
        print(
            f'  [{"OK " if app_bypass is False else "EKSIK"}] '
            f'{APP_DB_ROLE}.bypassrls={app_bypass} '
            f'(baglanti rolu={connect_bypass} - bu yuzden SET LOCAL ROLE sart)'
        )

    print('\nMigration tamamlandi.')


if __name__ == '__main__':
    main()
