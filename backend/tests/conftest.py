"""Pytest ortak fikstürleri.

Testler gercek Supabase veritabanina karsi kosar (uygulamanin tek veritabani
var). Bu yuzden her test kendi kayitlarini `tracker` fikstürüne bildirir ve
teardown'da HEPSI silinir - production tablolarinda test verisi kalmaz.

Ledger satirlari ORM uzerinden silinemez (degismezlik kurali). Temizlik
bilerek ham SQL ile yapilir; bu sadece test temizligine ozgudur.
"""
import sys
import time
import uuid
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
    ('stock_ledger_entries', 'id'),
    ('stock_transfer_items', 'id'),
    ('stock_transfers', 'id'),
    ('invoices', 'id'),
    ('sales_items', 'id'),
    ('sales', 'id'),
    ('products', 'id'),
    ('customers', 'id'),
    ('warehouses', 'id'),
]


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

    with engine.begin() as conn:
        existing = conn.execute(
            text('SELECT id FROM users WHERE email = :e'), {'e': TEST_ADMIN_EMAIL}
        ).first()
        if existing:
            user_id = existing[0]
            created_here = False
            conn.execute(
                text(
                    'UPDATE users SET hashed_password = :p, role = :r, is_active = TRUE '
                    'WHERE id = :i'
                ),
                {'p': hash_password(TEST_ADMIN_PASSWORD), 'r': 'admin', 'i': user_id},
            )
        else:
            user_id = conn.execute(
                text(
                    'INSERT INTO users (email, hashed_password, role, full_name, '
                    'is_active, created_at) '
                    "VALUES (:e, :p, 'admin', 'Pytest Admin', TRUE, NOW()) RETURNING id"
                ),
                {'e': TEST_ADMIN_EMAIL, 'p': hash_password(TEST_ADMIN_PASSWORD)},
            ).scalar()
            created_here = True

    yield user_id

    if created_here:
        with engine.begin() as conn:
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
            conn.execute(text('DELETE FROM users WHERE id = :i'), {'i': user_id})


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
        with engine.begin() as conn:
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
            for transfer_id in self._rows.get('stock_transfers', set()):
                for row in conn.execute(
                    text('SELECT id FROM stock_transfer_items WHERE transfer_id = :t'),
                    {'t': transfer_id},
                ):
                    self.add('stock_transfer_items', row[0])

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
