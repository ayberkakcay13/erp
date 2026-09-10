r"""Phase 10 migration: products.stock -> stok defteri (stock_ledger_entries).

Yaptiklari (hepsi IDEMPOTENT - iki kez calistirilirsa cift kayit atmaz):
  1. Yeni tablolari olusturur (warehouses, stock_ledger_entries, transfer'lar)
  2. `sales_items.warehouse_id` kolonunu ekler
  3. Para/miktar kolonlarini numeric(18, 4)'e cevirir (float yasagi)
  4. Varsayilan "Merkez Depo" kaydini olusturur
  5. Her urunun mevcut `products.stock` degerini reason='acilis' olarak ledger'a tasir
  6. Dogrulama: her urun icin stock == ledger toplami
  7. Dogrulama gecerse `products.stock` kolonunu kaldirir

Kullanim (backend/ klasorunden):
    .\env\Scripts\python.exe migrate_stock_to_ledger.py
"""
from decimal import Decimal

from sqlalchemy import inspect, text

from app.database import Base, engine
from app import models  # noqa: F401  -- modellerin Base'e kaydolmasi icin

DEFAULT_WAREHOUSE_CODE = 'MERKEZ'
DEFAULT_WAREHOUSE_NAME = 'Merkez Depo'

# (tablo, kolon) -> numeric(18, 4)'e cevrilecek para/miktar kolonlari
NUMERIC_COLUMNS = [
    ('products', 'price'),
    ('sales', 'total_amount'),
    ('sales_items', 'quantity'),
    ('sales_items', 'unit_price'),
    ('sales_items', 'total_price'),
    ('invoices', 'total_amount'),
]

# Phase 15: `sales`/`sales_items` -> `sales_orders`/`sales_order_items` olarak
# yeniden adlandirildi. Bu migration'in kendi idempotency testi (iki kez
# calistirilinca bozulmamali) hala gecerli olsun diye eski adlar gercek
# (guncel) tablo adina cozulur.
RENAMED_TABLES = {'sales': 'sales_orders', 'sales_items': 'sales_order_items'}


def table_exists(conn, table: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
        {'t': table},
    ).first() is not None


def resolve_table(conn, table: str) -> str:
    """Tablo Phase 15'te yeniden adlandirildiyse guncel adini doner."""
    if not table_exists(conn, table) and table in RENAMED_TABLES:
        return RENAMED_TABLES[table]
    return table


def column_exists(conn, table: str, column: str) -> bool:
    table = resolve_table(conn, table)
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
    print('Phase 10 migration basliyor (idempotent).')

    step(1, 'Yeni tablolar olusturuluyor')
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    for name in ('warehouses', 'stock_ledger_entries', 'stock_transfers',
                 'stock_transfer_items'):
        print(f'  [{"OK " if name in tables else "EKSIK"}] {name}')

    with engine.begin() as conn:
        sales_items_table = resolve_table(conn, 'sales_items')
        step(2, f'{sales_items_table}.warehouse_id kolonu')
        if column_exists(conn, 'sales_items', 'warehouse_id'):
            print('  zaten var, atlaniyor')
        else:
            conn.execute(
                text(f'ALTER TABLE {sales_items_table} ADD COLUMN warehouse_id INTEGER')
            )
            conn.execute(text(
                f'ALTER TABLE {sales_items_table} ADD CONSTRAINT '
                f'{sales_items_table}_warehouse_id_fkey '
                'FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)'
            ))
            print('  eklendi')

        step(3, 'Para/miktar kolonlari numeric(18, 4) yapiliyor')
        for raw_table, column in NUMERIC_COLUMNS:
            table = resolve_table(conn, raw_table)
            current = conn.execute(
                text(
                    'SELECT data_type, numeric_precision, numeric_scale '
                    'FROM information_schema.columns '
                    'WHERE table_name = :t AND column_name = :c'
                ),
                {'t': table, 'c': column},
            ).first()
            if current is None:
                print(f'  {table}.{column}: kolon yok, atlaniyor')
                continue
            if current[0] == 'numeric' and current[1] == 18 and current[2] == 4:
                print(f'  {table}.{column}: zaten numeric(18,4)')
                continue
            conn.execute(text(
                f'ALTER TABLE {table} ALTER COLUMN {column} '
                f'TYPE numeric(18, 4) USING {column}::numeric(18, 4)'
            ))
            print(f'  {table}.{column}: {current[0]} -> numeric(18,4)')

        step(4, 'Varsayilan depo')
        existing = conn.execute(
            text('SELECT id, name FROM warehouses WHERE code = :c'),
            {'c': DEFAULT_WAREHOUSE_CODE},
        ).first()
        if existing:
            warehouse_id = existing[0]
            print(f'  "{existing[1]}" zaten var (id={warehouse_id})')
        else:
            warehouse_id = conn.execute(
                text(
                    'INSERT INTO warehouses '
                    '(code, name, warehouse_type, is_active, is_default, created_at) '
                    "VALUES (:code, :name, 'merkez', TRUE, TRUE, NOW()) RETURNING id"
                ),
                {'code': DEFAULT_WAREHOUSE_CODE, 'name': DEFAULT_WAREHOUSE_NAME},
            ).scalar()
            print(f'  "{DEFAULT_WAREHOUSE_NAME}" olusturuldu (id={warehouse_id})')
        # Varsayilan tek olmali
        conn.execute(
            text('UPDATE warehouses SET is_default = FALSE WHERE id <> :id'),
            {'id': warehouse_id},
        )
        conn.execute(
            text('UPDATE warehouses SET is_default = TRUE WHERE id = :id'),
            {'id': warehouse_id},
        )

        step(5, 'products.stock -> ledger (reason=acilis)')
        if not column_exists(conn, 'products', 'stock'):
            print('  products.stock kolonu yok - tasima daha once yapilmis, atlaniyor')
            moved = skipped = 0
        else:
            rows = conn.execute(
                text('SELECT id, name, COALESCE(stock, 0) FROM products ORDER BY id')
            ).all()
            moved = skipped = 0
            for product_id, name, stock in rows:
                # Idempotentlik: bu urun icin acilis kaydi varsa tekrar atma
                has_opening = conn.execute(
                    text(
                        'SELECT 1 FROM stock_ledger_entries '
                        "WHERE product_id = :p AND reason = 'acilis'"
                    ),
                    {'p': product_id},
                ).first() is not None
                if has_opening:
                    skipped += 1
                    continue
                qty = Decimal(str(stock or 0))
                if qty == 0:
                    # Sifir stok icin hareket yazmiyoruz; bakiye zaten 0.
                    skipped += 1
                    continue
                conn.execute(
                    text(
                        'INSERT INTO stock_ledger_entries '
                        '(product_id, warehouse_id, change_qty, balance_qty, reason, '
                        ' ref_type, ref_id, note, created_at) '
                        "VALUES (:p, :w, :q, :q, 'acilis', 'opening', :p, "
                        "'Phase 10 migration: products.stock devri', NOW())"
                    ),
                    {'p': product_id, 'w': warehouse_id, 'q': qty},
                )
                moved += 1
            print(f'  {moved} urun tasindi, {skipped} urun atlandi (zaten var / 0 stok)')

        step(6, 'Dogrulama: products.stock == ledger toplami')
        mismatches = []
        if column_exists(conn, 'products', 'stock'):
            rows = conn.execute(text(
                'SELECT p.id, p.name, COALESCE(p.stock, 0) AS col_stock, '
                '       COALESCE(SUM(l.change_qty), 0) AS ledger_stock '
                'FROM products p '
                'LEFT JOIN stock_ledger_entries l ON l.product_id = p.id '
                'GROUP BY p.id, p.name, p.stock ORDER BY p.id'
            )).all()
            for product_id, name, col_stock, ledger_stock in rows:
                if Decimal(str(col_stock)) != Decimal(str(ledger_stock)):
                    mismatches.append((product_id, name, col_stock, ledger_stock))
            if mismatches:
                print(f'  {len(mismatches)} urunde fark var:')
                for product_id, name, col_stock, ledger_stock in mismatches:
                    print(f'    #{product_id} {name}: kolon={col_stock} ledger={ledger_stock}')
            else:
                print(f'  {len(rows)} urunun tamami tutarli')
        else:
            print('  kolon yok, dogrulama atlandi')

        step(7, 'products.stock kolonunun kaldirilmasi')
        if not column_exists(conn, 'products', 'stock'):
            print('  kolon zaten yok')
        elif mismatches:
            print('  ATLANDI: dogrulama gecmedi, kolon korunuyor. Farklari duzeltip tekrar calistirin.')
        else:
            conn.execute(text('ALTER TABLE products DROP COLUMN stock'))
            print('  products.stock kaldirildi')

    print('\nMigration tamamlandi.')


if __name__ == '__main__':
    main()
