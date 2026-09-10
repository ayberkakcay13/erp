r"""Phase 15 migration: satis zinciri refactoring (REFACTOR, YUKSEK RISK).

`Sale` -> `Quotation -> SalesOrder -> DeliveryNote -> Invoice` zincirine
bolunur. Mevcut veri ID'LERI KORUNARAK tasinir - `stock_ledger_entries` ve
`audit_logs` bu id'lere referans verir.

Yaptiklari (hepsi IDEMPOTENT):
  1. Backup: sales/sales_items/invoices -> *_backup tablolari (once)
  2. Rename: sales -> sales_orders, sales_items -> sales_order_items,
     sales_order_items.sale_id -> sales_order_id (once)
  3. Yeni tablolari olusturur (quotations, quotation_items, delivery_notes,
     delivery_note_items, invoice_items)
  4. sales_orders/sales_order_items/invoices/customers'a Phase 15 kolonlarini
     ekler
  5. so_number'i geriye donuk uretir (onayli/iptal siparisler icin)
  6. Eksik unique kisitini tamamlar (uq_sales_order_tenant_number)
  7. Onayli/iptal her SalesOrder icin DeliveryNote uretir (AYNI id ile) ve
     kalemlerini kopyalar; delivered_quantity'yi geriye donuk doldurur
  8. stock_ledger_entries.ref_type'i 'sale' -> 'delivery' cevirir
     (ref_id DEGISMEZ - DeliveryNote.id = SalesOrder.id)
  9. audit_logs.table_name'i 'sales'/'sales_items' -> yeni adlarina cevirir
 10. invoices.delivery_note_id'yi sale_id'den doldurur
 11. Yeni tablolarda RLS + politika + index + yetki kurar
 12. VALIDATION: satir sayilari, ledger tutarliligi, stok toplami - biri
     bozuksa SystemExit(1)

Kullanim (backend/ klasorunden):
    .\env\Scripts\python.exe migrate_phase15_sales.py
"""
from decimal import Decimal

from sqlalchemy import text

from app import models  # noqa: F401  Base.metadata'yi doldurur
from app.database import Base, engine

NEW_TABLES = [
    'quotations', 'quotation_items',
    'delivery_notes', 'delivery_note_items',
    'invoice_items',
]

RENAMED_TABLES = ['sales_orders', 'sales_order_items']

SALES_ORDER_COLUMNS = [
    ('so_number', 'VARCHAR(50)'),
    ('quotation_id', 'INTEGER REFERENCES quotations(id)'),
    ('promised_delivery_date', 'DATE'),
    ('warehouse_id', 'INTEGER REFERENCES warehouses(id)'),
    ('subtotal', 'NUMERIC(18, 4)'),
    ('tax_total', 'NUMERIC(18, 4)'),
    ('created_by', 'INTEGER REFERENCES users(id)'),
]

SALES_ORDER_ITEM_COLUMNS = [
    ('tax_rate', "NUMERIC(18, 4) NOT NULL DEFAULT 0"),
    ('delivered_quantity', 'NUMERIC(18, 4) NOT NULL DEFAULT 0'),
]

INVOICE_COLUMNS = [
    ('delivery_note_id', 'INTEGER REFERENCES delivery_notes(id)'),
    ('due_date', 'DATE'),
    ('subtotal', 'NUMERIC(18, 4)'),
    ('tax_total', 'NUMERIC(18, 4)'),
    ('payment_status', "VARCHAR(20) NOT NULL DEFAULT 'odenmedi'"),
    ('note', 'TEXT'),
]

CUSTOMER_COLUMNS = [
    ('credit_limit', 'NUMERIC(18, 4) NOT NULL DEFAULT 0'),
    ('credit_days', 'INTEGER NOT NULL DEFAULT 0'),
]

UNIQUE_CONSTRAINTS = [
    ('sales_orders', 'uq_sales_order_tenant_number', 'tenant_id, so_number'),
]

POLICY_NAME = 'tenant_isolation'
POLICY_EXPRESSION = (
    "(current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int)"
)
APP_DB_ROLE = 'erp_app'


def table_exists(conn, table: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
        {'t': table},
    ).first() is not None


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


def step(n, title: str) -> None:
    print(f'\n[{n}] {title}')


def _set_seq(conn, table: str) -> None:
    """Explicit id ile INSERT sonrasi sequence'i ileri alir."""
    conn.execute(text(
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
        f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
    ))


def main() -> None:
    print('Phase 15 migration basliyor (idempotent, YUKSEK RISK - refactor).')

    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))

        # ---------------- 0. Migrasyon oncesi stok anlik goruntusu ----------------
        pre_snapshot = {}
        if table_exists(conn, 'stock_ledger_entries'):
            pre_snapshot = dict(conn.execute(text(
                'SELECT product_id, SUM(change_qty) FROM stock_ledger_entries '
                'GROUP BY product_id'
            )).all())

        step(1, 'Backup: sales/sales_items/invoices')
        if table_exists(conn, 'sales') and not table_exists(conn, 'sales_backup'):
            conn.execute(text('CREATE TABLE sales_backup AS SELECT * FROM sales'))
            print('  sales_backup olusturuldu')
        else:
            print('  atlandi (sales yok ya da backup zaten var)')
        if table_exists(conn, 'sales_items') and not table_exists(conn, 'sales_items_backup'):
            conn.execute(text(
                'CREATE TABLE sales_items_backup AS SELECT * FROM sales_items'
            ))
            print('  sales_items_backup olusturuldu')
        if table_exists(conn, 'invoices') and not table_exists(conn, 'invoices_backup'):
            conn.execute(text('CREATE TABLE invoices_backup AS SELECT * FROM invoices'))
            print('  invoices_backup olusturuldu')

        step(2, 'Rename: sales -> sales_orders, sales_items -> sales_order_items')
        if table_exists(conn, 'sales') and not table_exists(conn, 'sales_orders'):
            conn.execute(text('ALTER TABLE sales RENAME TO sales_orders'))
            print('  sales -> sales_orders')
        else:
            print('  atlandi (zaten yeniden adlandirilmis)')
        if table_exists(conn, 'sales_items') and not table_exists(conn, 'sales_order_items'):
            conn.execute(text('ALTER TABLE sales_items RENAME TO sales_order_items'))
            print('  sales_items -> sales_order_items')
        if column_exists(conn, 'sales_order_items', 'sale_id') and not column_exists(
            conn, 'sales_order_items', 'sales_order_id'
        ):
            conn.execute(text(
                'ALTER TABLE sales_order_items RENAME COLUMN sale_id TO sales_order_id'
            ))
            print('  sales_order_items.sale_id -> sales_order_id')

        step(3, 'Yeni tablolar olusturuluyor')
        # DIKKAT: bind=engine YENI bir baglanti acar; henuz commit edilmemis
        # rename'i goremez ve ayni tabloya kilit beklerken timeout'a duser.
        # Ayni transaction/connection (`conn`) uzerinde calismali.
        Base.metadata.create_all(bind=conn)
        for name in NEW_TABLES + RENAMED_TABLES:
            exists = table_exists(conn, name)
            print(f'  [{"OK " if exists else "EKSIK"}] {name}')

        step(4, 'sales_orders / sales_order_items / invoices / customers kolonlari')
        for table, columns in (
            ('sales_orders', SALES_ORDER_COLUMNS),
            ('sales_order_items', SALES_ORDER_ITEM_COLUMNS),
            ('invoices', INVOICE_COLUMNS),
            ('customers', CUSTOMER_COLUMNS),
        ):
            added = []
            for column, ddl in columns:
                if column_exists(conn, table, column):
                    continue
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
                added.append(column)
            print(f'  {table}: {"eklendi -> " + ", ".join(added) if added else "zaten var"}')

        step(5, 'so_number geriye donuk uretiliyor')
        # DIKKAT: 'SO-{yil}-{sira}' formati kullanilmaz - naming_service'in
        # canli sayaci da ayni formatta ilk numarayi ('SO-2026-00001') uretir
        # ve cakisir. Gecmis kayitlar bariz sekilde 'migrasyon' oldugu
        # belli olan, farkli bir bicimle isaretlenir.
        filled = conn.execute(text(
            "UPDATE sales_orders SET so_number = 'SO-MIG-' || id "
            'WHERE so_number IS NULL AND docstatus IN (1, 2)'
        )).rowcount
        print(f'  {filled} siparise so_number atandi (gecmis format: SO-MIG-<id>)')

        step(6, 'Eksik unique kisitlari')
        added = []
        for table, name, columns in UNIQUE_CONSTRAINTS:
            if constraint_exists(conn, name):
                continue
            conn.execute(text(f'ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({columns})'))
            added.append(name)
        print(f'  {"eklendi -> " + ", ".join(added) if added else "zaten var"}')

        step(7, 'Onayli/iptal SalesOrder icin DeliveryNote uretiliyor (AYNI id)')
        # DIKKAT: yalnizca sales_backup'taki (migration ONCESI var olan)
        # id'ler islenir. Canli sales_orders/delivery_notes id sekansi
        # birbirinden BAGIMSIZDIR (ayri sequence) - migration sonrasi
        # uygulama tarafindan uretilen bir SO ile alakasiz bir DN AYNI id'yi
        # tasiyabilir. Backup'a scope etmeden 'NOT EXISTS (dn.id = so.id)'
        # kontrolu bu tesadufi id cakismalarinda yanlis pozitif/negatif
        # uretir. Backup yoksa (script Phase 15 sonrasi ilk kez, backup
        # olmadan calistirilirsa) bu adim atlanir - islenecek gecmis veri yok.
        created = 0
        item_count = 0
        filled = 0
        if table_exists(conn, 'sales_backup'):
            created = conn.execute(text(
                "INSERT INTO delivery_notes "
                "(id, tenant_id, delivery_note_number, sales_order_id, customer_id, "
                " warehouse_id, delivery_date, docstatus, submitted_at, submitted_by, "
                " cancelled_at, cancelled_by, cancel_reason, created_by, created_at, note) "
                "SELECT so.id, so.tenant_id, NULL, so.id, so.customer_id, "
                "       so.warehouse_id, so.sale_date, so.docstatus, so.submitted_at, "
                "       so.submitted_by, so.cancelled_at, so.cancelled_by, so.cancel_reason, "
                "       so.created_by, so.created_at, "
                "       'Migration Phase 15: eski Sale onayindan uretildi' "
                "FROM sales_orders so "
                "WHERE so.docstatus IN (1, 2) "
                "  AND so.id IN (SELECT id FROM sales_backup WHERE docstatus IN (1, 2)) "
                "  AND NOT EXISTS (SELECT 1 FROM delivery_notes dn WHERE dn.id = so.id)"
            )).rowcount
            _set_seq(conn, 'delivery_notes')

            item_count = conn.execute(text(
                "INSERT INTO delivery_note_items "
                "(tenant_id, delivery_note_id, sales_order_item_id, product_id, uom_id, "
                " warehouse_id, quantity, unit_price, stock_quantity, item_status) "
                "SELECT soi.tenant_id, soi.sales_order_id, soi.id, soi.product_id, "
                "       soi.uom_id, soi.warehouse_id, soi.quantity, soi.unit_price, "
                "       soi.stock_quantity, 'sevk_edildi' "
                "FROM sales_order_items soi "
                "JOIN sales_orders so ON so.id = soi.sales_order_id "
                "WHERE so.docstatus IN (1, 2) "
                "  AND so.id IN (SELECT id FROM sales_backup WHERE docstatus IN (1, 2)) "
                "  AND NOT EXISTS ("
                "    SELECT 1 FROM delivery_note_items dni "
                "    WHERE dni.sales_order_item_id = soi.id"
                "  )"
            )).rowcount
            _set_seq(conn, 'delivery_note_items')

            filled = conn.execute(text(
                'UPDATE sales_order_items soi SET delivered_quantity = soi.quantity '
                'FROM sales_orders so '
                'WHERE so.id = soi.sales_order_id AND so.docstatus = 1 '
                '  AND so.id IN (SELECT id FROM sales_backup WHERE docstatus = 1) '
                '  AND soi.delivered_quantity = 0'
            )).rowcount
        print(f'  {created} DeliveryNote uretildi (id = SalesOrder.id)')
        print(f'  {item_count} DeliveryNoteItem kopyalandi')
        print(f'  {filled} kalemde delivered_quantity geriye donuk dolduruldu')

        step(8, "stock_ledger_entries.ref_type 'sale' -> 'delivery'")
        remapped = conn.execute(text(
            "UPDATE stock_ledger_entries SET ref_type = 'delivery' "
            "WHERE reason IN ('satis', 'satis_iptal') AND ref_type = 'sale'"
        )).rowcount
        print(f'  {remapped} ledger satiri yeniden etiketlendi')

        step(9, "audit_logs.table_name 'sales'/'sales_items' -> yeni adlar")
        r1 = conn.execute(text(
            "UPDATE audit_logs SET table_name = 'sales_orders' WHERE table_name = 'sales'"
        )).rowcount
        r2 = conn.execute(text(
            "UPDATE audit_logs SET table_name = 'sales_order_items' "
            "WHERE table_name = 'sales_items'"
        )).rowcount
        print(f'  sales: {r1}, sales_items: {r2}')

        step(10, 'invoices.delivery_note_id sale_id uzerinden dolduruluyor')
        # Ayni id-cakismasi riski: yalnizca gecmis (invoices_backup'taki)
        # faturalar icin, ve yalnizca migrasyonun URETTIGI (backup kapsamli)
        # DeliveryNote'lara isaret edildiginden emin olunarak doldurulur.
        filled = 0
        if table_exists(conn, 'invoices_backup') and table_exists(conn, 'sales_backup'):
            filled = conn.execute(text(
                'UPDATE invoices SET delivery_note_id = sale_id '
                'WHERE delivery_note_id IS NULL AND sale_id IS NOT NULL '
                '  AND id IN (SELECT id FROM invoices_backup) '
                '  AND sale_id IN (SELECT id FROM sales_backup WHERE docstatus IN (1, 2)) '
                '  AND sale_id IN (SELECT id FROM delivery_notes)'
            )).rowcount
        print(f'  {filled} faturada delivery_note_id baglandi')

        step(11, 'Yeni tablolarda tenant_id NOT NULL + RLS')
        for table in NEW_TABLES:
            orphans = conn.execute(
                text(f'SELECT count(*) FROM {table} WHERE tenant_id IS NULL')
            ).scalar()
            if orphans:
                print(f'  {table}: {orphans} satirda tenant_id bos, NOT NULL atlandi')
            else:
                conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL'))
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

        # ---------------- 12. Validation ----------------
        step(12, 'Validation')
        errors = []

        # DIKKAT: sales_backup TEK SEFERLIK bir anlik goruntu; migration sonrasi
        # normal kullanim yeni sales_orders satirlari ekler (asla silmez). Bu
        # yuzden esitlik degil, "hic kucculmedi" kontrolu yapilir.
        if table_exists(conn, 'sales_backup'):
            backup_count = conn.execute(text('SELECT count(*) FROM sales_backup')).scalar()
            order_count = conn.execute(text('SELECT count(*) FROM sales_orders')).scalar()
            ok = order_count >= backup_count
            print(f'  [{"OK " if ok else "HATA"}] sales_backup={backup_count} '
                  f'sales_orders={order_count} (>= olmali)')
            if not ok:
                errors.append('sales_orders satir sayisi sales_backup\'tan kucuk - veri kaybi')

        # Bu kontrol yalnizca MIGRATION'IN URETTIGI DeliveryNote'lari sayar -
        # yeni akista bir SalesOrder'in DeliveryNote'suz onaylanmasi NORMALDIR
        # (stok hareketi ayri, opsiyonel bir belgeye tasindi), o yuzden CANLI
        # SO/DN sayilari zamanla birbirinden ayrisir; bu beklenen davranistir.
        if table_exists(conn, 'sales_backup'):
            backup_confirmed = conn.execute(text(
                'SELECT count(*) FROM sales_backup WHERE docstatus IN (1, 2)'
            )).scalar()
            migrated_dn = conn.execute(text(
                "SELECT count(*) FROM delivery_notes "
                "WHERE note = 'Migration Phase 15: eski Sale onayindan uretildi'"
            )).scalar()
            ok = backup_confirmed == migrated_dn
            print(f'  [{"OK " if ok else "HATA"}] gecmis onayli/iptal SO={backup_confirmed} '
                  f'migrasyonun urettigi DeliveryNote={migrated_dn}')
            if not ok:
                errors.append(
                    'Migrasyonun urettigi DeliveryNote sayisi gecmis onayli/iptal '
                    'SalesOrder sayisiyla uyusmuyor'
                )

        leftover = conn.execute(text(
            "SELECT count(*) FROM stock_ledger_entries "
            "WHERE reason IN ('satis', 'satis_iptal') AND ref_type = 'sale'"
        )).scalar()
        ok = leftover == 0
        print(f'  [{"OK " if ok else "HATA"}] eski ref_type=sale kalintisi: {leftover}')
        if not ok:
            errors.append(f"{leftover} ledger satiri hala ref_type='sale' tasiyor")

        dangling = conn.execute(text(
            "SELECT count(*) FROM stock_ledger_entries sle "
            "WHERE sle.ref_type = 'delivery' "
            "  AND NOT EXISTS (SELECT 1 FROM delivery_notes dn WHERE dn.id = sle.ref_id)"
        )).scalar()
        ok = dangling == 0
        print(f'  [{"OK " if ok else "HATA"}] sahipsiz ref_type=delivery satiri: {dangling}')
        if not ok:
            errors.append(f'{dangling} ledger satirinin ref_id\'sine karsilik gelen DeliveryNote yok')

        if pre_snapshot:
            post_snapshot = dict(conn.execute(text(
                'SELECT product_id, SUM(change_qty) FROM stock_ledger_entries '
                'GROUP BY product_id'
            )).all())
            mismatches = [
                pid for pid, qty in pre_snapshot.items()
                if Decimal(str(post_snapshot.get(pid, 0))) != Decimal(str(qty))
            ]
            ok = not mismatches
            print(f'  [{"OK " if ok else "HATA"}] stok toplami degismedi '
                  f'({len(pre_snapshot)} urun kontrol edildi)')
            if not ok:
                errors.append(f'Stok toplami degisen urunler: {mismatches}')

        if errors:
            print('\nMIGRATION DOGRULAMASI BASARISIZ:')
            for err in errors:
                print(f'  - {err}')
            raise SystemExit(1)

    print('\nMigration tamamlandi ve dogrulandi.')


if __name__ == '__main__':
    main()
