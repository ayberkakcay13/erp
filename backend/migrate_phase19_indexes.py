r"""Phase 19 migration: Musteri/urun detay endpoint'leri icin eksik indeksler
(DUSUK RISK, IDEMPOTENT - satir/tablo silmez, sadece CREATE INDEX IF NOT EXISTS).

Phase 19'da /api/customers/{id}/orders, /api/products/{id}/orders ve
/api/sales/trend gibi endpoint'ler artik gercek sales_orders/sales_order_items
tablolarini sorguluyor. Postgres foreign key kolonlarini otomatik indekslemez;
bu script en cok sorgulanan kolonlara indeks ekler.

Kullanim (backend/ klasorunden):
    .\env\Scripts\python.exe migrate_phase19_indexes.py
"""
from sqlalchemy import text

from app.database import engine

INDEXES = [
    ('ix_sales_orders_customer_id', 'sales_orders', 'customer_id'),
    ('ix_sales_orders_sale_date', 'sales_orders', 'sale_date'),
    ('ix_sales_order_items_product_id', 'sales_order_items', 'product_id'),
    ('ix_sales_order_items_sales_order_id', 'sales_order_items', 'sales_order_id'),
]


def run():
    with engine.begin() as conn:
        for name, table, column in INDEXES:
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})'))
            print(f'  {name} ({table}.{column}) OK')
    print('Phase 19 index migration tamamlandi.')


if __name__ == '__main__':
    run()
