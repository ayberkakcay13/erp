"""Phase 10 testleri: stok defteri, depo yonetimi ve transfer.

Notion "Phase 10 - Adim 8" listesindeki her madde burada bir testtir.
"""
import threading
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import SessionLocal, engine
from app.models import LedgerImmutableError, StockLedgerEntry
from app.services import stock_service
from tests.conftest import unique_suffix


# ---------------- Yardimcilar ----------------

def make_customer(client, tracker, name='Test Musteri'):
    suffix = unique_suffix()
    response = client.post('/api/customers', json={
        'name': name,
        'email': f'p10-{suffix}@erptest.com',
        'phone': '05550000000',
    })
    assert response.status_code == 201, response.text
    customer = response.json()
    tracker.add('customers', customer['id'])
    return customer


def make_product(client, tracker, stock='100', price='10.00', warehouse_id=None):
    suffix = unique_suffix()
    body = {
        'name': f'P10 Urun {suffix}',
        'sku': f'P10-{suffix}',
        'price': price,
        'stock': stock,
    }
    if warehouse_id is not None:
        body['warehouse_id'] = warehouse_id
    response = client.post('/api/products', json=body)
    assert response.status_code == 201, response.text
    product = response.json()
    tracker.add('products', product['id'])
    return product


def make_warehouse(client, tracker, wtype='sube'):
    suffix = unique_suffix()
    response = client.post('/api/warehouses', json={
        'code': f'P10-{suffix}'[:50],
        'name': f'Test Depo {suffix}',
        'warehouse_type': wtype,
    })
    assert response.status_code == 201, response.text
    warehouse = response.json()
    tracker.add('warehouses', warehouse['id'])
    return warehouse


def make_sale(client, tracker, customer_id, items):
    response = client.post('/api/sales', json={
        'customer_id': customer_id,
        'items': items,
    })
    if response.status_code == 201:
        tracker.add('sales', response.json()['id'])
    return response


def stock_of(client, product_id, warehouse_id=None):
    params = {'warehouse_id': warehouse_id} if warehouse_id else {}
    response = client.get(f'/api/products/{product_id}', params=params)
    assert response.status_code == 200, response.text
    return Decimal(str(response.json()['stock']))


# ---------------- 1. Acilis kaydi ----------------

def test_acilis_kaydi_bakiyeyi_dogru_kurar(client, tracker):
    product = make_product(client, tracker, stock='42')

    assert Decimal(str(product['stock'])) == Decimal('42')
    assert stock_of(client, product['id']) == Decimal('42')

    ledger = client.get('/api/stock/ledger', params={'product_id': product['id']})
    assert ledger.status_code == 200
    entries = ledger.json()
    assert len(entries) == 1
    assert entries[0]['reason'] == 'acilis'
    assert entries[0]['ref_type'] == 'opening'
    assert Decimal(str(entries[0]['change_qty'])) == Decimal('42')
    assert Decimal(str(entries[0]['balance_qty'])) == Decimal('42')


def test_hareketsiz_urun_sifir_stok(client, tracker):
    product = make_product(client, tracker, stock='0')
    assert stock_of(client, product['id']) == Decimal('0')
    assert client.get('/api/stock/ledger',
                      params={'product_id': product['id']}).json() == []


# ---------------- 2. Satis ledger'a dusuyor mu ----------------

def test_satis_ledgera_negatif_hareket_yazar(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='20', price='50.00')

    response = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 3, 'unit_price': '50.00'},
    ])
    assert response.status_code == 201, response.text
    sale = response.json()

    assert stock_of(client, product['id']) == Decimal('17')

    entries = client.get('/api/stock/ledger', params={
        'product_id': product['id'], 'reason': 'satis'}).json()
    assert len(entries) == 1
    assert Decimal(str(entries[0]['change_qty'])) == Decimal('-3')
    assert Decimal(str(entries[0]['balance_qty'])) == Decimal('17')
    assert entries[0]['ref_type'] == 'sale'
    assert entries[0]['ref_id'] == sale['id']


def test_ayni_urun_iki_satirda_toplam_uzerinden_duser(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')

    response = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 4, 'unit_price': '10.00'},
        {'product_id': product['id'], 'quantity': 6, 'unit_price': '10.00'},
    ])
    assert response.status_code == 201, response.text
    assert stock_of(client, product['id']) == Decimal('0')


# ---------------- 3. Iptal ve geri alma ----------------

def test_iptal_stogu_geri_ekler(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='20')

    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 5, 'unit_price': '10.00'},
    ]).json()
    assert stock_of(client, product['id']) == Decimal('15')

    response = client.put(f'/api/sales/{sale["id"]}', json={'status': 'cancelled'})
    assert response.status_code == 200, response.text
    assert stock_of(client, product['id']) == Decimal('20')

    entries = client.get('/api/stock/ledger', params={
        'product_id': product['id'], 'reason': 'satis_iptal'}).json()
    assert len(entries) == 1
    assert Decimal(str(entries[0]['change_qty'])) == Decimal('5')


def test_iptal_edilen_satis_tekrar_acilamaz(client, tracker):
    """Phase 11 kurali Phase 4/10'daki "iptali geri al" davranisinin yerini aldi:
    iptal edilmis belge tekrar onaylanamaz, duzeltme icin yeni satis kesilir.
    """
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='20')

    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 5, 'unit_price': '10.00'},
    ]).json()
    client.put(f'/api/sales/{sale["id"]}', json={'status': 'cancelled'})
    assert stock_of(client, product['id']) == Decimal('20')

    response = client.put(f'/api/sales/{sale["id"]}', json={'status': 'completed'})
    assert response.status_code == 400, response.text
    assert 'tekrar acilamaz' in response.json()['detail']
    # Stok iptalden sonraki halinde kalir
    assert stock_of(client, product['id']) == Decimal('20')


def test_ayni_durumu_tekrar_gondermek_stogu_degistirmez(client, tracker):
    """Idempotentlik: tekrarlanan durum gecisleri ikinci kez stok hareketi yazmaz."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='20')

    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 5, 'unit_price': '10.00'},
    ]).json()

    # pending <-> completed is durumu gecisleri stogu etkilemez
    client.put(f'/api/sales/{sale["id"]}', json={'status': 'completed'})
    client.put(f'/api/sales/{sale["id"]}', json={'status': 'pending'})
    assert stock_of(client, product['id']) == Decimal('15')

    # Iptal bir kez isler; tekrari sessizce yok sayilir
    client.put(f'/api/sales/{sale["id"]}', json={'status': 'cancelled'})
    client.put(f'/api/sales/{sale["id"]}', json={'status': 'cancelled'})
    client.put(f'/api/sales/{sale["id"]}', json={'status': 'cancelled'})
    assert stock_of(client, product['id']) == Decimal('20')


# ---------------- 4. Yetersiz stok ----------------

def test_yetersiz_stokta_400_ve_kayit_olusmaz(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='3')

    response = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 5, 'unit_price': '10.00'},
    ])
    assert response.status_code == 400, response.text
    assert 'stok yetersiz' in response.json()['detail']
    assert stock_of(client, product['id']) == Decimal('3')

    # Yarim satis olusmamis olmali
    assert client.get('/api/sales', params={'customer_id': customer['id']}).json() == []


def test_taslak_satis_onayinda_stok_yetmezse_400(client, tracker):
    """Taslak satis stok tutmaz; onay aninda stok yetmiyorsa 400 doner."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')

    draft = client.post('/api/sales', json={
        'customer_id': customer['id'],
        'save_as_draft': True,
        'items': [{'product_id': product['id'], 'quantity': 10, 'unit_price': '10.00'}],
    })
    assert draft.status_code == 201, draft.text
    tracker.add('sales', draft.json()['id'])
    assert stock_of(client, product['id']) == Decimal('10')  # taslak stok tutmaz

    # Stogu baska bir satisla tuket
    other = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 10, 'unit_price': '10.00'},
    ])
    assert other.status_code == 201
    assert stock_of(client, product['id']) == Decimal('0')

    response = client.post(f'/api/sales/{draft.json()["id"]}/submit')
    assert response.status_code == 400, response.text
    assert 'stok yetersiz' in response.json()['detail']


# ---------------- 5. Depo ve transfer ----------------

def test_depo_crud(client, tracker):
    warehouse = make_warehouse(client, tracker)
    assert warehouse['warehouse_type'] == 'sube'

    response = client.put(f'/api/warehouses/{warehouse["id"]}',
                          json={'name': 'Guncellenmis Depo'})
    assert response.status_code == 200
    assert response.json()['name'] == 'Guncellenmis Depo'

    listed = client.get('/api/warehouses').json()
    assert any(w['id'] == warehouse['id'] for w in listed)
    # Varsayilan depo migration'da olusturuldu
    assert any(w['is_default'] for w in listed)


def test_depo_kendi_ust_deposu_olamaz(client, tracker):
    warehouse = make_warehouse(client, tracker)
    response = client.put(f'/api/warehouses/{warehouse["id"]}',
                          json={'parent_id': warehouse['id']})
    assert response.status_code == 400


def test_transfer_toplam_stogu_degistirmez(client, tracker):
    """Korunum kontrolu: transfer sonrasi iki deponun toplami sabit kalir."""
    source = make_warehouse(client, tracker)
    target = make_warehouse(client, tracker)
    product = make_product(client, tracker, stock='30', warehouse_id=source['id'])

    before_total = stock_of(client, product['id'])
    assert before_total == Decimal('30')
    assert stock_of(client, product['id'], source['id']) == Decimal('30')
    assert stock_of(client, product['id'], target['id']) == Decimal('0')

    response = client.post('/api/transfers', json={
        'from_warehouse_id': source['id'],
        'to_warehouse_id': target['id'],
        'items': [{'product_id': product['id'], 'quantity': 12}],
    })
    assert response.status_code == 201, response.text
    transfer = response.json()
    tracker.add('stock_transfers', transfer['id'])
    assert transfer['transfer_no'].startswith('TR-')

    assert stock_of(client, product['id'], source['id']) == Decimal('18')
    assert stock_of(client, product['id'], target['id']) == Decimal('12')
    assert stock_of(client, product['id']) == before_total  # toplam degismedi

    entries = client.get('/api/stock/ledger',
                         params={'product_id': product['id']}).json()
    reasons = {e['reason'] for e in entries}
    assert 'transfer_cikis' in reasons and 'transfer_giris' in reasons


def test_transfer_yetersiz_stokta_400(client, tracker):
    source = make_warehouse(client, tracker)
    target = make_warehouse(client, tracker)
    product = make_product(client, tracker, stock='5', warehouse_id=source['id'])

    response = client.post('/api/transfers', json={
        'from_warehouse_id': source['id'],
        'to_warehouse_id': target['id'],
        'items': [{'product_id': product['id'], 'quantity': 50}],
    })
    assert response.status_code == 400, response.text
    assert stock_of(client, product['id'], source['id']) == Decimal('5')


def test_ayni_depoya_transfer_reddedilir(client, tracker):
    warehouse = make_warehouse(client, tracker)
    product = make_product(client, tracker, stock='5', warehouse_id=warehouse['id'])
    response = client.post('/api/transfers', json={
        'from_warehouse_id': warehouse['id'],
        'to_warehouse_id': warehouse['id'],
        'items': [{'product_id': product['id'], 'quantity': 1}],
    })
    assert response.status_code == 400


# ---------------- 6. Ledger degismezligi ----------------

def test_ledger_satiri_update_edilemez(client, tracker):
    product = make_product(client, tracker, stock='10')
    session = SessionLocal()
    try:
        entry = session.query(StockLedgerEntry).filter(
            StockLedgerEntry.product_id == product['id']
        ).first()
        assert entry is not None
        entry.change_qty = Decimal('999')
        with pytest.raises(LedgerImmutableError):
            session.flush()
    finally:
        session.rollback()
        session.close()


def test_ledger_satiri_delete_edilemez(client, tracker):
    product = make_product(client, tracker, stock='10')
    session = SessionLocal()
    try:
        entry = session.query(StockLedgerEntry).filter(
            StockLedgerEntry.product_id == product['id']
        ).first()
        assert entry is not None
        session.delete(entry)
        with pytest.raises(LedgerImmutableError):
            session.flush()
    finally:
        session.rollback()
        session.close()


def test_duzeltme_ters_kayitla_yapilir(client, tracker):
    product = make_product(client, tracker, stock='10')

    response = client.post('/api/stock/adjustments', json={
        'product_id': product['id'],
        'change_qty': '-4',
        'reason': 'fire',
        'note': 'Kirilma',
    })
    assert response.status_code == 201, response.text
    assert stock_of(client, product['id']) == Decimal('6')

    entries = client.get('/api/stock/ledger',
                         params={'product_id': product['id']}).json()
    assert len(entries) == 2  # acilis silinmedi, uzerine hareket eklendi


def test_negatif_stoga_dusuren_duzeltme_reddedilir(client, tracker):
    product = make_product(client, tracker, stock='5')
    response = client.post('/api/stock/adjustments', json={
        'product_id': product['id'],
        'change_qty': '-9',
        'reason': 'fire',
    })
    assert response.status_code == 400
    assert stock_of(client, product['id']) == Decimal('5')


# ---------------- 7. Es zamanlilik ----------------

def test_es_zamanli_iki_satis_stogu_eksiye_dusurmez(client, tracker):
    """Iki thread ayni anda son 1 adedi almaya calisir; biri hata almalidir.

    `stock_service.add_entry` urun satirini `SELECT ... FOR UPDATE` ile
    kilitledigi icin ikinci transaction birincinin commit'ini bekler ve
    guncel (0) bakiyeyi gorur.
    """
    product = make_product(client, tracker, stock='1')
    product_id = product['id']
    warehouse_id = None
    results = []
    barrier = threading.Barrier(2)

    def take_one():
        session = SessionLocal()
        try:
            barrier.wait(timeout=30)
            stock_service.add_entry(
                session, product_id, warehouse_id, Decimal('-1'), 'satis',
                ref_type='sale', ref_id=None,
            )
            session.commit()
            results.append('ok')
        except Exception as exc:  # noqa: BLE001 - hangi hata oldugu onemli degil
            session.rollback()
            results.append(f'fail: {type(exc).__name__}')
        finally:
            session.close()

    threads = [threading.Thread(target=take_one) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert results.count('ok') == 1, f'beklenen 1 basari, gelen: {results}'
    assert stock_of(client, product_id) == Decimal('0')


# ---------------- 8. Raporlar ve endpointler ----------------

def test_low_stock_ledger_uzerinden_hesaplanir(client, tracker):
    product = make_product(client, tracker, stock='2')
    response = client.get('/api/alerts/low-stock', params={'threshold': 5})
    assert response.status_code == 200
    items = {item['id']: item for item in response.json()['items']}
    assert product['id'] in items
    assert Decimal(str(items[product['id']]['stock'])) == Decimal('2')


def test_stock_balance_ve_warehouse_stock(client, tracker):
    warehouse = make_warehouse(client, tracker)
    product = make_product(client, tracker, stock='7', warehouse_id=warehouse['id'])

    balance = client.get('/api/stock/balance',
                         params={'product_id': product['id']}).json()
    assert len(balance) == 1
    assert balance[0]['warehouse_id'] == warehouse['id']
    assert Decimal(str(balance[0]['quantity'])) == Decimal('7')

    warehouse_stock = client.get(f'/api/warehouses/{warehouse["id"]}/stock').json()
    assert any(row['product_id'] == product['id'] for row in warehouse_stock)


def test_urun_stok_gecmisi_endpointi(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'},
    ])

    response = client.get(f'/api/stock/product/{product["id"]}/history')
    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(str(body['total_stock'])) == Decimal('8')
    assert len(body['entries']) == 2
    assert body['entries'][0]['reason'] == 'satis'  # en yeni once
    assert len(body['by_warehouse']) == 1


def test_hareketi_olan_urun_ve_depo_silinemez(client, tracker):
    warehouse = make_warehouse(client, tracker)
    product = make_product(client, tracker, stock='5', warehouse_id=warehouse['id'])

    assert client.delete(f'/api/products/{product["id"]}').status_code == 409
    assert client.delete(f'/api/warehouses/{warehouse["id"]}').status_code == 409


# ---------------- 9. Semasal kontroller ----------------

def test_products_stock_kolonu_kaldirildi():
    with engine.connect() as conn:
        found = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'products' AND column_name = 'stock'"
        )).first()
    assert found is None, 'products.stock kolonu hala duruyor'


def test_para_ve_miktar_kolonlari_numeric():
    """Float yasagi: para/miktar kolonlari numeric(18, 4) olmali."""
    expected = [
        ('products', 'price'),
        ('sales', 'total_amount'),
        ('sales_items', 'quantity'),
        ('sales_items', 'unit_price'),
        ('sales_items', 'total_price'),
        ('invoices', 'total_amount'),
        ('stock_ledger_entries', 'change_qty'),
        ('stock_ledger_entries', 'balance_qty'),
    ]
    with engine.connect() as conn:
        for table, column in expected:
            row = conn.execute(
                text(
                    'SELECT data_type, numeric_precision, numeric_scale '
                    'FROM information_schema.columns '
                    'WHERE table_name = :t AND column_name = :c'
                ),
                {'t': table, 'c': column},
            ).first()
            assert row is not None, f'{table}.{column} yok'
            assert row[0] == 'numeric', f'{table}.{column} numeric degil: {row[0]}'
            assert (row[1], row[2]) == (18, 4), f'{table}.{column} = {row[1]},{row[2]}'


def test_migration_iki_kez_calisinca_cift_kayit_atmaz(client, tracker):
    """Idempotentlik: acilis kaydi olan urune ikinci kez acilis yazilmaz."""
    product = make_product(client, tracker, stock='11')

    import migrate_stock_to_ledger

    migrate_stock_to_ledger.main()
    migrate_stock_to_ledger.main()

    entries = client.get('/api/stock/ledger', params={
        'product_id': product['id'], 'reason': 'acilis'}).json()
    assert len(entries) == 1
    assert stock_of(client, product['id']) == Decimal('11')
