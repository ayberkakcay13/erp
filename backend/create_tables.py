r"""Supabase'de models.py'deki tablolari olusturur ve dogrular.

Kullanim (backend/ klasorunden):
    .\env\Scripts\python.exe create_tables.py
"""
from sqlalchemy import inspect, text

from app.database import Base, engine
from app import models  # noqa: F401  -- modellerin Base'e kaydolmasi icin gerekli

EXPECTED = ['customers', 'products', 'sales', 'sales_items', 'invoices', 'users']

print('Tablolar olusturuluyor...')
Base.metadata.create_all(bind=engine)

inspector = inspect(engine)
existing = inspector.get_table_names()

print('\nSupabase public schema tablolari:')
for name in EXPECTED:
    mark = 'OK ' if name in existing else 'EKSIK'
    print(f'  [{mark}] {name}')

missing = [n for n in EXPECTED if n not in existing]
if missing:
    raise SystemExit(f'\nHATA: su tablolar olusmadi: {missing}')

print('\nSELECT testi (satir sayilari):')
with engine.connect() as conn:
    for name in EXPECTED:
        count = conn.execute(text(f'SELECT COUNT(*) FROM {name}')).scalar()
        print(f'  {name}: {count} satir')

print('\nTum tablolar hazir.')
