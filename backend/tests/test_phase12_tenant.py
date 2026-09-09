"""Phase 12 testleri: cok kiracili izolasyon, RLS ve modul aktivasyonu.

Notion "Phase 12 - Adim 7" listesindeki her madde burada bir testtir.
Bu fazin kalbi SIZINTI TESTLERI: diger her sey calissa da bir tenant
digerinin verisini gorebiliyorsa faz basarisiz sayilir.
"""
import threading

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.services import tenant_context
from tests.conftest import admin_connection, unique_suffix


# ---------------- Kurulum yardimcilari ----------------

@pytest.fixture()
def superadmin_client(client, admin_user):
    """Test admin'ini gecici olarak platform sahibi yapar.

    Tenant olusturma superadmin yetkisi ister; test bitince yetki geri alinir.
    """
    user_id = admin_user['user_id']
    with admin_connection() as conn:
        conn.execute(
            text('UPDATE users SET is_superadmin = TRUE WHERE id = :i'), {'i': user_id}
        )
    # Yetki token'da tasiniyor, yeniden giris gerekiyor
    login = client.post('/api/auth/login', json={
        'email': 'pytest-admin@erptest.com', 'password': 'pytest-admin-123'})
    assert login.status_code == 200, login.text
    client.headers['Authorization'] = f'Bearer {login.json()["access_token"]}'
    yield client
    with admin_connection() as conn:
        conn.execute(
            text('UPDATE users SET is_superadmin = FALSE WHERE id = :i'), {'i': user_id}
        )


class TenantHandle:
    """Bir test tenant'i ve o tenant'in kullanicisiyla konusan istemci."""

    def __init__(self, tenant_id, slug, client, email, password):
        self.id = tenant_id
        self.slug = slug
        self.client = client
        self.email = email
        self.password = password


# Cocuk tablodan ebeveyne dogru silme sirasi (FK ihlali olmasin)
TENANT_DELETE_ORDER = (
    'purchase_invoice_items',
    'purchase_invoices',
    'purchase_receipt_items',
    'purchase_receipts',
    'purchase_order_items',
    'purchase_orders',
    'suppliers',
    'product_variant_attributes',
    'product_barcodes',
    'uom_conversions',
    'stock_ledger_entries',
    'stock_transfer_items',
    'stock_transfers',
    'invoices',
    'sales_items',
    'sales',
    'audit_logs',
    'products',
    'item_attribute_values',
    'item_attributes',
    'customers',
    'warehouses',
    'uoms',
    'item_groups',
    'brands',
    'naming_series',
    'users',
    'tenant_modules',
)


def _cleanup_tenant(tenant_id: int) -> None:
    """Test tenant'ina ait TUM satirlari siler - production'da iz kalmaz."""
    with admin_connection() as conn:
        # Bu tenant'in kullanicilarinin BASKA tablolarda biraktigi izler once
        # temizlenir; yoksa users silinirken FK ihlali olur.
        user_ids = [
            r[0] for r in conn.execute(
                text('SELECT id FROM users WHERE tenant_id = :t'), {'t': tenant_id}
            )
        ] or [0]
        conn.execute(
            text('DELETE FROM audit_logs WHERE user_id = ANY(:u)'), {'u': user_ids}
        )
        for table in ('sales', 'invoices', 'stock_transfers', 'purchase_orders',
                      'purchase_receipts', 'purchase_invoices'):
            for column in ('submitted_by', 'cancelled_by'):
                conn.execute(
                    text(f'UPDATE {table} SET {column} = NULL WHERE {column} = ANY(:u)'),
                    {'u': user_ids},
                )
        for table in ('stock_ledger_entries', 'stock_transfers', 'purchase_orders',
                      'purchase_receipts', 'purchase_invoices'):
            conn.execute(
                text(f'UPDATE {table} SET created_by = NULL WHERE created_by = ANY(:u)'),
                {'u': user_ids},
            )

        for table in TENANT_DELETE_ORDER:
            conn.execute(
                text(f'DELETE FROM {table} WHERE tenant_id = :t'), {'t': tenant_id}
            )
        conn.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': tenant_id})


@pytest.fixture()
def two_tenants(superadmin_client):
    """Iki bagimsiz tenant + her birine giris yapmis birer kullanici."""
    from fastapi.testclient import TestClient

    from app.main import app

    created = []
    handles = []
    try:
        for label in ('a', 'b'):
            suffix = unique_suffix().replace('_', '-')
            slug = f'p12-{label}-{suffix}'[:63]
            email = f'p12-{label}-{suffix}@erptest.com'
            password = 'tenant-test-123'
            response = superadmin_client.post('/api/tenants', json={
                'name': f'Phase 12 Test {label.upper()}',
                'slug': slug,
                'plan': 'pro',
                'admin_email': email,
                'admin_password': password,
                'admin_full_name': f'Tenant {label.upper()} Admin',
            })
            assert response.status_code == 201, response.text
            tenant_id = response.json()['id']
            created.append(tenant_id)

            tenant_client = TestClient(app)
            login = tenant_client.post(
                '/api/auth/login', json={'email': email, 'password': password}
            )
            assert login.status_code == 200, login.text
            tenant_client.headers['Authorization'] = (
                f'Bearer {login.json()["access_token"]}'
            )
            handles.append(TenantHandle(tenant_id, slug, tenant_client, email, password))
        yield handles
    finally:
        for handle in handles:
            handle.client.close()
        for tenant_id in created:
            _cleanup_tenant(tenant_id)


def seed(handle: TenantHandle, sku_suffix: str = ''):
    """Tenant'a bir musteri, bir urun ve bir satis ekler."""
    suffix = unique_suffix()
    customer = handle.client.post('/api/customers', json={
        'name': f'Musteri {handle.slug}',
        'email': f'musteri-{suffix}@erptest.com',
    })
    assert customer.status_code == 201, customer.text
    customer = customer.json()

    product = handle.client.post('/api/products', json={
        'name': f'Urun {handle.slug}',
        'sku': sku_suffix or f'P12-{suffix}',
        'price': '100.00',
        'stock': '50',
    })
    assert product.status_code == 201, product.text
    product = product.json()

    sale = handle.client.post('/api/sales', json={
        'customer_id': customer['id'],
        'items': [{'product_id': product['id'], 'quantity': 2, 'unit_price': '100.00'}],
    })
    assert sale.status_code == 201, sale.text
    return {'customer': customer, 'product': product, 'sale': sale.json()}


# ---------------- 1. Tenant kurulumu ----------------

def test_tenant_olusturma_calisir_halde_gelir(two_tenants):
    """Yeni firma: moduller, varsayilan depo ve numaralandirma serileri hazir."""
    a = two_tenants[0]

    warehouses = a.client.get('/api/warehouses').json()
    assert len(warehouses) == 1
    assert warehouses[0]['code'] == 'MERKEZ'
    assert warehouses[0]['is_default'] is True

    modules = a.client.get('/api/tenant/modules').json()
    assert modules['tenant_id'] == a.id
    assert 'sales' in modules['enabled']

    tenant = a.client.get('/api/tenant').json()
    assert tenant['id'] == a.id
    assert tenant['slug'] == a.slug


def test_tenant_admini_superadmin_degil(two_tenants):
    """Musteri firmanin yoneticisi platform islemlerini yapamaz."""
    a = two_tenants[0]
    response = a.client.get('/api/tenants')
    assert response.status_code == 403, response.text


# ---------------- 2. Izolasyon (bu fazin kalbi) ----------------

def test_liste_sadece_kendi_tenantini_gosterir(two_tenants):
    a, b = two_tenants
    data_a = seed(a)
    data_b = seed(b)

    customers_a = {c['id'] for c in a.client.get('/api/customers').json()}
    customers_b = {c['id'] for c in b.client.get('/api/customers').json()}

    assert data_a['customer']['id'] in customers_a
    assert data_b['customer']['id'] not in customers_a
    assert data_a['customer']['id'] not in customers_b
    assert customers_a.isdisjoint(customers_b)


def test_baska_tenantin_kaydi_404_doner(two_tenants):
    """403 degil 404: "yetkin yok" demek kaydin varligini sizdirirdi."""
    a, b = two_tenants
    data_b = seed(b)

    for path in (
        f"/api/customers/{data_b['customer']['id']}",
        f"/api/products/{data_b['product']['id']}",
        f"/api/sales/{data_b['sale']['id']}",
    ):
        response = a.client.get(path)
        assert response.status_code == 404, f'{path} -> {response.status_code}'


def test_baska_tenantin_kaydi_guncellenemez_silinemez(two_tenants):
    a, b = two_tenants
    data_b = seed(b)

    update = a.client.put(
        f"/api/customers/{data_b['customer']['id']}", json={'name': 'Ele gecirildi'}
    )
    assert update.status_code == 404, update.text

    delete = a.client.delete(f"/api/products/{data_b['product']['id']}")
    assert delete.status_code == 404, delete.text

    # B'nin kaydi bozulmamis olmali
    unchanged = b.client.get(f"/api/customers/{data_b['customer']['id']}").json()
    assert unchanged['name'] != 'Ele gecirildi'


def test_raporlar_tenant_bazli(two_tenants):
    a, b = two_tenants
    seed(a)
    seed(b)

    top_a = a.client.get('/api/reports/top-products').json()
    skus_a = {row['sku'] for row in top_a}
    top_b = b.client.get('/api/reports/top-products').json()
    skus_b = {row['sku'] for row in top_b}
    assert skus_a.isdisjoint(skus_b)

    # Stok raporu da tenant bazli
    balance_a = {row['sku'] for row in a.client.get('/api/stock/balance').json()}
    balance_b = {row['sku'] for row in b.client.get('/api/stock/balance').json()}
    assert balance_a.isdisjoint(balance_b)


def test_denetim_izi_tenant_bazli(two_tenants):
    a, b = two_tenants
    data_a = seed(a)
    seed(b)

    logs_a = a.client.get('/api/audit-log', params={'limit': 500}).json()
    assert logs_a, 'A tenant\'inin log kaydi yok'
    assert any(
        log['table_name'] == 'customers' and log['record_id'] == data_a['customer']['id']
        for log in logs_a
    )
    # B'nin kayitlarina ait satir gorunmemeli
    customers_b = {c['id'] for c in b.client.get('/api/customers').json()}
    assert not any(
        log['table_name'] == 'customers' and log['record_id'] in customers_b
        for log in logs_a
    )


def test_ayni_urun_kodu_iki_tenantta_kullanilabilir(two_tenants):
    """Unique kisitlar tenant bazli: UNIQUE(tenant_id, sku)."""
    a, b = two_tenants
    shared_sku = f'ORTAK-{unique_suffix()}'

    first = a.client.post('/api/products', json={
        'name': 'A firmasinin urunu', 'sku': shared_sku,
        'price': '10.00', 'stock': '5'})
    assert first.status_code == 201, first.text

    second = b.client.post('/api/products', json={
        'name': 'B firmasinin urunu', 'sku': shared_sku,
        'price': '20.00', 'stock': '7'})
    assert second.status_code == 201, second.text

    # Ayni tenant icinde hala tekil
    duplicate = a.client.post('/api/products', json={
        'name': 'Kopya', 'sku': shared_sku, 'price': '10.00', 'stock': '1'})
    assert duplicate.status_code == 409, duplicate.text


def test_fatura_numaralari_tenant_bazli_baslar(two_tenants):
    """Her firmanin kendi FT-YYYY-00001 dizisi olur."""
    a, b = two_tenants
    sale_a = seed(a)['sale']
    sale_b = seed(b)['sale']

    invoice_a = a.client.post(f"/api/sales/{sale_a['id']}/invoice", json={})
    invoice_b = b.client.post(f"/api/sales/{sale_b['id']}/invoice", json={})
    assert invoice_a.status_code == 201, invoice_a.text
    assert invoice_b.status_code == 201, invoice_b.text
    assert invoice_a.json()['invoice_number'].endswith('-00001')
    assert invoice_b.json()['invoice_number'].endswith('-00001')


# ---------------- 3. RLS: veritabani seviyesinde izolasyon ----------------

def test_rls_ham_sql_ile_bile_sizmiyor(two_tenants):
    """Uygulama filtresi olmadan, ham SQL ile bile diger tenant gorunmuyor.

    Bu testin degeri: `WHERE tenant_id = ?` HIC yazilmiyor. Satirlarin
    filtrelenmesini yapan sey yalnizca PostgreSQL RLS politikasi.
    """
    a, b = two_tenants
    data_a = seed(a)
    data_b = seed(b)

    with tenant_context.tenant_scope(a.id):
        session = SessionLocal()
        try:
            rows = session.execute(text('SELECT id FROM customers')).all()
            visible = {row[0] for row in rows}
        finally:
            session.close()

    assert data_a['customer']['id'] in visible
    assert data_b['customer']['id'] not in visible, 'RLS sizdirdi'


def test_rls_tenant_baglami_yoksa_hicbir_satir_donmez(two_tenants):
    """Baglam kurulmamis bir session hicbir is verisi goremez (guvenli varsayilan)."""
    a, _ = two_tenants
    seed(a)

    with tenant_context.tenant_scope(None):
        session = SessionLocal()
        try:
            count = session.execute(text('SELECT count(*) FROM customers')).scalar()
        finally:
            session.close()
    assert count == 0, f'tenant baglami yokken {count} satir gorundu'


def test_rls_yanlis_tenant_id_ile_insert_reddedilir(two_tenants):
    """WITH CHECK: baska tenant adina satir yazilamaz."""
    a, b = two_tenants

    with tenant_context.tenant_scope(a.id):
        session = SessionLocal()
        try:
            with pytest.raises(Exception) as excinfo:
                session.execute(
                    text(
                        'INSERT INTO customers (tenant_id, name, email, created_at) '
                        'VALUES (:t, :n, :e, NOW())'
                    ),
                    {'t': b.id, 'n': 'Sizinti denemesi', 'e': f'x-{unique_suffix()}@e.com'},
                )
                session.commit()
            assert 'row-level security' in str(excinfo.value).lower()
        finally:
            session.rollback()
            session.close()


def test_rls_tum_tenantli_tablolarda_zorlanmis():
    """RLS acik VE force edilmis olmali.

    FORCE olmadan politikalar tablo sahibini atlar; uygulama Supabase'e
    tablo sahibi rolle baglandigi icin izolasyon hic calismazdi.
    """
    from migrate_phase12_tenant import TENANT_TABLES

    with admin_connection() as conn:
        for table in TENANT_TABLES:
            enabled, forced = conn.execute(
                text(
                    'SELECT c.relrowsecurity, c.relforcerowsecurity '
                    'FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
                    "WHERE c.relname = :t AND n.nspname = 'public'"
                ),
                {'t': table},
            ).first()
            assert enabled, f'{table}: RLS kapali'
            assert forced, f'{table}: FORCE ROW LEVEL SECURITY yok'


def test_pooler_set_local_sizmiyor(two_tenants):
    """Supabase Transaction Pooler ile `SET LOCAL` sizintisi var mi?

    Notion Phase 12 / Adim 5'teki uyari: pooler baglantiyi paylastigi icin
    `SET` bir sonraki kullaniciya sizabilir. Burada ayni havuzdan arka arkaya
    ve es zamanli baglantilar alinip her birinin YALNIZCA kendi tenant'ini
    gordugu dogrulanir.
    """
    a, b = two_tenants
    data_a = seed(a)
    data_b = seed(b)
    expected = {a.id: data_a['customer']['id'], b.id: data_b['customer']['id']}
    forbidden = {a.id: data_b['customer']['id'], b.id: data_a['customer']['id']}

    leaks = []
    lock = threading.Lock()

    def read_as(tenant_id):
        with tenant_context.tenant_scope(tenant_id):
            session = SessionLocal()
            try:
                rows = {
                    row[0]
                    for row in session.execute(text('SELECT id FROM customers')).all()
                }
                session.commit()
                if expected[tenant_id] not in rows:
                    with lock:
                        leaks.append(f'tenant {tenant_id} kendi kaydini goremedi')
                if forbidden[tenant_id] in rows:
                    with lock:
                        leaks.append(f'tenant {tenant_id} digerinin kaydini gordu')
            finally:
                session.close()

    # Ardisik: ayni baglanti havuzdan tekrar alindiginda onceki SET kalmis mi
    for _ in range(6):
        read_as(a.id)
        read_as(b.id)

    # Es zamanli: farkli tenant'lar ayni havuzu paylasirken
    threads = [
        threading.Thread(target=read_as, args=(a.id if i % 2 == 0 else b.id,))
        for i in range(10)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert leaks == [], leaks


# ---------------- 4. Modul aktivasyonu ----------------

def test_kapali_modul_endpointi_403(two_tenants, superadmin_client):
    a, _ = two_tenants

    # Stok modulunu kapat
    response = superadmin_client.put(f'/api/tenants/{a.id}/modules', json={
        'modules': ['sales', 'invoice', 'reports']})
    assert response.status_code == 200, response.text

    blocked = a.client.get('/api/stock/balance')
    assert blocked.status_code == 403, blocked.text
    assert 'aktif degil' in blocked.json()['detail']

    # Acik modul calismaya devam ediyor
    assert a.client.get('/api/customers').status_code == 200

    modules = a.client.get('/api/tenant/modules').json()
    assert 'stock' not in modules['enabled']

    # Geri ac
    superadmin_client.put(f'/api/tenants/{a.id}/modules', json={
        'modules': ['sales', 'invoice', 'reports', 'stock']})
    assert a.client.get('/api/stock/balance').status_code == 200


def test_modul_listesi_frontend_icin_donuyor(two_tenants):
    a, _ = two_tenants
    modules = a.client.get('/api/tenant/modules').json()
    assert set(modules['enabled']).issubset(set(modules['all']))
    assert 'manufacturing' in modules['all']


# ---------------- 5. Superadmin ----------------

def test_superadmin_tum_tenantlari_gorur(two_tenants, superadmin_client):
    a, b = two_tenants
    tenants = {t['id'] for t in superadmin_client.get('/api/tenants').json()}
    assert a.id in tenants and b.id in tenants


def test_superadmin_tenant_filtresinden_muaf(two_tenants, superadmin_client):
    """Platform sahibi tum tenant'larin verisini gorebilir."""
    a, b = two_tenants
    data_a = seed(a)
    data_b = seed(b)

    visible = {c['id'] for c in superadmin_client.get(
        '/api/customers', params={'limit': 500}).json()}
    assert data_a['customer']['id'] in visible
    assert data_b['customer']['id'] in visible


# ---------------- 6. Semasal kontroller ----------------

def test_tenant_bazli_unique_kisitlari_var():
    expected = {
        'uq_products_tenant_sku',
        'uq_customers_tenant_email',
        'uq_warehouses_tenant_code',
        'uq_invoices_tenant_number',
        'uq_transfers_tenant_number',
    }
    with admin_connection() as conn:
        names = {
            row[0] for row in conn.execute(text('SELECT conname FROM pg_constraint'))
        }
    assert expected.issubset(names), expected - names

    # Eski global kisitlar kaldirilmis olmali
    stale = {'products_sku_key', 'customers_email_key', 'warehouses_code_key'}
    assert stale.isdisjoint(names), stale & names


def test_migration_iki_kez_calisinca_bozulmaz():
    import migrate_phase12_tenant

    migrate_phase12_tenant.main()
    migrate_phase12_tenant.main()

    with admin_connection() as conn:
        duplicates = conn.execute(text(
            'SELECT count(*) FROM ('
            '  SELECT slug FROM tenants GROUP BY slug HAVING count(*) > 1'
            ') d'
        )).scalar()
    assert duplicates == 0
