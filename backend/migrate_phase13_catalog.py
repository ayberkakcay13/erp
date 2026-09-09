r"""Phase 13 migration: olcu birimi, kategori, marka, barkod ve varyant yapisi.

Yaptiklari (hepsi IDEMPOTENT):
  1. Yeni tablolari olusturur (uoms, uom_conversions, item_groups, brands,
     product_barcodes, item_attributes, item_attribute_values,
     product_variant_attributes)
  2. products tablosuna urun karti kolonlarini ekler
  3. sales_items tablosuna uom_id + stock_quantity ekler ve mevcut satirlarda
     stock_quantity'yi quantity ile doldurur
  4. Tablo daha once olustuysa create_all'in ekleyemedigi unique kisitlari
     tamamlar (uq_barcodes_tenant_code vb.)
  5. Her tenant icin varsayilan olcu birimlerini ve evrensel donusumleri acar
  6. stock_uom_id bos olan urunleri "adet" birimine baglar
  7. Yeni tablolarda tenant_id'yi NOT NULL yapar, RLS'i acar ve izolasyon
     politikasini kurar (Phase 12 kurali)

Kullanim (backend/ klasorunden):
    .\env\Scripts\python.exe migrate_phase13_catalog.py
"""
from decimal import Decimal

from sqlalchemy import inspect, text

from app.database import Base, engine
from app.models import DEFAULT_CONVERSIONS, DEFAULT_UOMS

NEW_TABLES = [
    'uoms', 'uom_conversions', 'item_groups', 'brands', 'product_barcodes',
    'item_attributes', 'item_attribute_values', 'product_variant_attributes',
]

# (tablo, kisit adi, kolonlar) - tablo daha once olustuysa create_all bunlari
# EKLEMEZ; Phase 13 testi kisitlarin varligini pg_constraint'te ariyor.
UNIQUE_CONSTRAINTS = [
    ('uoms', 'uq_uoms_tenant_code', 'tenant_id, code'),
    ('uom_conversions', 'uq_uom_conversion',
     'tenant_id, from_uom_id, to_uom_id, product_id'),
    ('item_groups', 'uq_item_groups_tenant_code', 'tenant_id, code'),
    ('brands', 'uq_brands_tenant_name', 'tenant_id, name'),
    ('product_barcodes', 'uq_barcodes_tenant_code', 'tenant_id, barcode'),
    ('item_attributes', 'uq_item_attributes_tenant_name', 'tenant_id, name'),
    ('item_attribute_values', 'uq_attribute_value', 'attribute_id, value'),
    ('product_variant_attributes', 'uq_variant_attribute', 'product_id, attribute_id'),
]

# (kolon, DDL) - products tablosuna eklenecek urun karti alanlari
PRODUCT_COLUMNS = [
    ('stock_uom_id', 'INTEGER REFERENCES uoms(id)'),
    ('purchase_uom_id', 'INTEGER REFERENCES uoms(id)'),
    ('sales_uom_id', 'INTEGER REFERENCES uoms(id)'),
    ('item_group_id', 'INTEGER REFERENCES item_groups(id)'),
    ('brand_id', 'INTEGER REFERENCES brands(id)'),
    ("product_type", "VARCHAR(20) NOT NULL DEFAULT 'stoklu'"),
    ('is_active', 'BOOLEAN NOT NULL DEFAULT TRUE'),
    ('description', 'TEXT'),
    ('image_url', 'VARCHAR(500)'),
    ('min_stock_level', 'NUMERIC(18, 4)'),
    ('max_stock_level', 'NUMERIC(18, 4)'),
    ('is_variant_template', 'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('parent_product_id', 'INTEGER REFERENCES products(id)'),
]

SALES_ITEM_COLUMNS = [
    ('uom_id', 'INTEGER REFERENCES uoms(id)'),
    ('stock_quantity', 'NUMERIC(18, 4)'),
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
    print('Phase 13 migration basliyor (idempotent).')

    step(1, 'Yeni tablolar olusturuluyor')
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    for name in NEW_TABLES:
        print(f'  [{"OK " if name in tables else "EKSIK"}] {name}')

    with engine.begin() as conn:
        # RLS altinda calisiyoruz; migration muafiyetle ilerler (transaction'a bagli)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))

        step(2, 'products urun karti kolonlari')
        added = []
        for column, ddl in PRODUCT_COLUMNS:
            if column_exists(conn, 'products', column):
                continue
            conn.execute(text(f'ALTER TABLE products ADD COLUMN {column} {ddl}'))
            added.append(column)
        print(f'  {"eklendi -> " + ", ".join(added) if added else "zaten var"}')

        step(3, 'sales_items birim kolonlari')
        added = []
        for column, ddl in SALES_ITEM_COLUMNS:
            if column_exists(conn, 'sales_items', column):
                continue
            conn.execute(text(f'ALTER TABLE sales_items ADD COLUMN {column} {ddl}'))
            added.append(column)
        print(f'  {"eklendi -> " + ", ".join(added) if added else "zaten var"}')
        # Eski kalemler tek birimliydi: stok miktari = girilen miktar
        filled = conn.execute(text(
            'UPDATE sales_items SET stock_quantity = quantity '
            'WHERE stock_quantity IS NULL'
        )).rowcount
        print(f'  {filled} eski kalemde stock_quantity dolduruldu')

        step(4, 'Eksik unique kisitlari')
        for table, name, columns in UNIQUE_CONSTRAINTS:
            if constraint_exists(conn, name):
                continue
            # Kisit yoksa once cakisan satirlar temizlenmeli; burada yalnizca
            # ekleme denenir, cakisma varsa hata gorunur olsun diye yutulmaz.
            conn.execute(
                text(f'ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({columns})')
            )
            print(f'  eklendi -> {name}')

        step(5, 'Tenant bazli varsayilan olcu birimleri')
        tenant_ids = [r[0] for r in conn.execute(text('SELECT id FROM tenants ORDER BY id'))]
        if not tenant_ids:
            print('  tenant yok - once Phase 12 migration calistirilmali')
        for tenant_id in tenant_ids:
            codes = {}
            for code, name, is_integer in DEFAULT_UOMS:
                row = conn.execute(
                    text('SELECT id FROM uoms WHERE tenant_id = :t AND code = :c'),
                    {'t': tenant_id, 'c': code},
                ).first()
                if row:
                    codes[code] = row[0]
                    continue
                codes[code] = conn.execute(
                    text(
                        'INSERT INTO uoms (tenant_id, code, name, is_integer, '
                        'is_active, created_at) '
                        'VALUES (:t, :c, :n, :i, TRUE, NOW()) RETURNING id'
                    ),
                    {'t': tenant_id, 'c': code, 'n': name, 'i': is_integer},
                ).scalar()

            for from_code, to_code, factor in DEFAULT_CONVERSIONS:
                source, target = codes.get(from_code), codes.get(to_code)
                if source is None or target is None:
                    continue
                conn.execute(
                    text(
                        'INSERT INTO uom_conversions '
                        '(tenant_id, from_uom_id, to_uom_id, factor, product_id, '
                        ' created_at) '
                        'SELECT :t, :f, :o, :fac, NULL, NOW() WHERE NOT EXISTS ('
                        '  SELECT 1 FROM uom_conversions WHERE tenant_id = :t '
                        '    AND from_uom_id = :f AND to_uom_id = :o '
                        '    AND product_id IS NULL)'
                    ),
                    {'t': tenant_id, 'f': source, 'o': target,
                     'fac': Decimal(factor)},
                )

            # Birimsiz urunler "adet" olsun
            updated = conn.execute(
                text(
                    'UPDATE products SET stock_uom_id = :u '
                    'WHERE tenant_id = :t AND stock_uom_id IS NULL'
                ),
                {'u': codes['adet'], 't': tenant_id},
            ).rowcount
            print(
                f'  tenant {tenant_id}: {len(codes)} birim hazir, '
                f'{updated} urun "adet" birimine baglandi'
            )

        step(6, 'tenant_id NOT NULL + RLS')
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

        # Yeni tablolar icin uygulama rolune yetki
        conn.execute(text(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public '
            f'TO {APP_DB_ROLE}'
        ))
        conn.execute(text(
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_DB_ROLE}'
        ))
        print(f'  {APP_DB_ROLE} yetkileri tazelendi')

        step(7, 'Dogrulama')
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
        missing_uom = conn.execute(
            text('SELECT count(*) FROM products WHERE stock_uom_id IS NULL')
        ).scalar()
        print(f'  stok birimi olmayan urun: {missing_uom}')

    print('\nMigration tamamlandi.')


if __name__ == '__main__':
    main()
