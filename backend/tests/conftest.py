"""Pytest ortak fikstürleri.

Testler gercek Supabase veritabanina karsi kosar (uygulamanin tek veritabani
var). Bu yuzden her test kendi kayitlarini `tracker` fikstürüne bildirir ve
teardown'da HEPSI silinir - production tablolarinda test verisi kalmaz.

Ledger satirlari ORM uzerinden silinemez (degismezlik kurali). Temizlik
bilerek ham SQL ile yapilir; bu sadece test temizligine ozgudur.

Phase 12: tablolar RLS + FORCE ROW LEVEL SECURITY altinda. Ham SQL ile
calisan kurulum/temizlik baglantilari `app.bypass_rls` ayarini acikca
acmak zorunda - aksi halde DELETE hicbir satira dokunmaz.
"""
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402

TEST_ADMIN_EMAIL = 'pytest-admin@erptest.com'
TEST_ADMIN_PASSWORD = 'pytest-admin-123'

# Silme sirasi FK bagimliliklarini takip eder (once cocuk, sonra ebeveyn)
CLEANUP_ORDER = [
    ('audit_logs', 'id'),
    # Phase 13 tablolari urunlerden ONCE silinmeli (FK)
    ('product_variant_attributes', 'id'),
    ('product_barcodes', 'id'),
    ('uom_conversions', 'id'),
    ('stock_ledger_entries', 'id'),
    ('stock_transfer_items', 'id'),
    ('stock_transfers', 'id'),
    ('invoices', 'id'),
    ('sales_items', 'id'),
    ('sales', 'id'),
    ('products', 'id'),
    ('item_attribute_values', 'id'),
    ('item_attributes', 'id'),
    ('customers', 'id'),
    ('warehouses', 'id'),
    ('item_groups', 'id'),
    ('brands', 'id'),
]


@contextmanager
def admin_connection():
    """RLS muafiyetli ham SQL baglantisi (yalnizca test kurulumu/temizligi)."""
    with engine.begin() as conn:
        # 3. parametre true = SET LOCAL: ayar transaction ile sinirli kalir.
        # false (oturum duzeyi) verilirse Supabase Transaction Pooler
        # baglantiyi havuza geri verdiginde muafiyet sonraki kiraciya sizar.
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        yield conn


def unique_suffix() -> str:
    """Testler paralel/tekrarli kosarken cakismayan benzersiz ek."""
    return f'{int(time.time())}-{uuid.uuid4().hex[:6]}'


@pytest.fixture(scope='session')
def admin_user():
    """Testlere ozel admin kullanicisi.

    API'den kayit yapilamaz (ilk kullanici disindaki kayitlar admin token'i
    ister), bu yuzden dogrudan veritabanina yazilir ve oturum sonunda silinir -
    production tablosunda test kullanicisi kalmaz.
    """
    from app.auth import hash_password

    with admin_connection() as conn:
        tenant_id = conn.execute(
            text("SELECT id FROM tenants WHERE slug = 'varsayilan'")
        ).scalar()
        existing = conn.execute(
            text('SELECT id FROM users WHERE email = :e'), {'e': TEST_ADMIN_EMAIL}
        ).first()
        if existing:
            user_id = existing[0]
            created_here = False
            conn.execute(
                text(
                    'UPDATE users SET hashed_password = :p, role = :r, is_active = TRUE, '
                    'tenant_id = :t, is_superadmin = FALSE WHERE id = :i'
                ),
                {
                    'p': hash_password(TEST_ADMIN_PASSWORD), 'r': 'admin',
                    't': tenant_id, 'i': user_id,
                },
            )
        else:
            user_id = conn.execute(
                text(
                    'INSERT INTO users (email, hashed_password, role, full_name, '
                    'is_active, tenant_id, is_superadmin, created_at) '
                    "VALUES (:e, :p, 'admin', 'Pytest Admin', TRUE, :t, FALSE, NOW()) "
                    'RETURNING id'
                ),
                {
                    'e': TEST_ADMIN_EMAIL, 'p': hash_password(TEST_ADMIN_PASSWORD),
                    't': tenant_id,
                },
            ).scalar()
            created_here = True

    yield {'user_id': user_id, 'tenant_id': tenant_id}

    if created_here:
        with admin_connection() as conn:
            # Test kayitlari temizlendikten sonra kullaniciya bagli iz kalmamali
            conn.execute(
                text('UPDATE stock_ledger_entries SET created_by = NULL '
                     'WHERE created_by = :i'),
                {'i': user_id},
            )
            conn.execute(
                text('UPDATE stock_transfers SET created_by = NULL WHERE created_by = :i'),
                {'i': user_id},
            )
            for column in ('submitted_by', 'cancelled_by'):
                for table in ('sales', 'invoices', 'stock_transfers'):
                    conn.execute(
                        text(f'UPDATE {table} SET {column} = NULL WHERE {column} = :i'),
                        {'i': user_id},
                    )
            conn.execute(
                text('DELETE FROM audit_logs WHERE user_id = :i'), {'i': user_id}
            )
            conn.execute(text('DELETE FROM users WHERE id = :i'), {'i': user_id})


@pytest.fixture(scope='session')
def default_tenant_id(admin_user) -> int:
    """Testlerin uzerinde calistigi varsayilan tenant."""
    return admin_user['tenant_id']


@pytest.fixture(scope='session')
def admin_token(admin_user) -> str:
    """Test admin kullanicisiyla giris yapip token doner."""
    with TestClient(app) as client:
        response = client.post(
            '/api/auth/login',
            json={'email': TEST_ADMIN_EMAIL, 'password': TEST_ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return response.json()['access_token']


@pytest.fixture()
def client(admin_token):
    """Admin token'i onceden takili TestClient."""
    with TestClient(app) as test_client:
        test_client.headers.update({'Authorization': f'Bearer {admin_token}'})
        yield test_client


class Tracker:
    """Test icinde olusturulan kayitlari toplar, teardown'da siler."""

    def __init__(self):
        self._rows: dict[str, set] = {}

    def add(self, table: str, row_id) -> None:
        if row_id is not None:
            self._rows.setdefault(table, set()).add(row_id)

    def add_many(self, table: str, row_ids) -> None:
        for row_id in row_ids:
            self.add(table, row_id)

    def cleanup(self) -> None:
        with admin_connection() as conn:
            # Once takip edilen belgelere bagli tum yan kayitlari topla
            for sale_id in self._rows.get('sales', set()):
                for row in conn.execute(
                    text('SELECT id FROM invoices WHERE sale_id = :s'), {'s': sale_id}
                ):
                    self.add('invoices', row[0])
                for row in conn.execute(
                    text('SELECT id FROM sales_items WHERE sale_id = :s'), {'s': sale_id}
                ):
                    self.add('sales_items', row[0])
            for product_id in self._rows.get('products', set()):
                for row in conn.execute(
                    text('SELECT id FROM stock_ledger_entries WHERE product_id = :p'),
                    {'p': product_id},
                ):
                    self.add('stock_ledger_entries', row[0])
                for row in conn.execute(
                    text('SELECT id FROM stock_transfer_items WHERE product_id = :p'),
                    {'p': product_id},
                ):
                    self.add('stock_transfer_items', row[0])
                # Phase 13: barkod, varyant ozniteligi, urune ozel donusum
                for table in ('product_barcodes', 'product_variant_attributes',
                              'uom_conversions'):
                    for row in conn.execute(
                        text(f'SELECT id FROM {table} WHERE product_id = :p'),
                        {'p': product_id},
                    ):
                        self.add(table, row[0])
            for warehouse_id in self._rows.get('warehouses', set()):
                for row in conn.execute(
                    text(
                        'SELECT id FROM stock_transfers '
                        'WHERE from_warehouse_id = :w OR to_warehouse_id = :w'
                    ),
                    {'w': warehouse_id},
                ):
                    self.add('stock_transfers', row[0])
                for row in conn.execute(
                    text('SELECT id FROM stock_ledger_entries WHERE warehouse_id = :w'),
                    {'w': warehouse_id},
                ):
                    self.add('stock_ledger_entries', row[0])
            for attribute_id in self._rows.get('item_attributes', set()):
                for row in conn.execute(
                    text('SELECT id FROM item_attribute_values WHERE attribute_id = :a'),
                    {'a': attribute_id},
                ):
                    self.add('item_attribute_values', row[0])

            for transfer_id in self._rows.get('stock_transfers', set()):
                for row in conn.execute(
                    text('SELECT id FROM stock_transfer_items WHERE transfer_id = :t'),
                    {'t': transfer_id},
                ):
                    self.add('stock_transfer_items', row[0])

            # Phase 11: takip edilen kayitlarin denetim izi satirlari da silinir
            audited = {
                'sales': 'sales', 'products': 'products', 'customers': 'customers',
                'invoices': 'invoices', 'warehouses': 'warehouses',
                'stock_transfers': 'stock_transfers', 'sales_items': 'sales_items',
                'stock_transfer_items': 'stock_transfer_items',
            }
            for table, log_table in audited.items():
                ids = self._rows.get(table)
                if not ids:
                    continue
                for row in conn.execute(
                    text(
                        'SELECT id FROM audit_logs '
                        'WHERE table_name = :t AND record_id = ANY(:ids)'
                    ),
                    {'t': log_table, 'ids': list(ids)},
                ):
                    self.add('audit_logs', row[0])

            for table, pk in CLEANUP_ORDER:
                ids = self._rows.get(table)
                if not ids:
                    continue
                conn.execute(
                    text(f'DELETE FROM {table} WHERE {pk} = ANY(:ids)'),
                    {'ids': list(ids)},
                )
        self._rows.clear()


@pytest.fixture()
def tracker():
    tracked = Tracker()
    yield tracked
    tracked.cleanup()
