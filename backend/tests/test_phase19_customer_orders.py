"""Phase 19: musteri detay modal'i endpoint'leri - GERCEK sales_orders verisi.

Phase 18'in mock-varsayimli testlerinin yerini alir. Her test kendi musteri/
urun/siparisini olusturur (tracker ile temizlenir), boylece diger testlerin
veya paralel calisan faz suitelerinin verisine bagimli degildir.
"""
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from tests.test_phase10_stock import make_customer, make_product, make_sale


def test_orders_gercek_siparisi_dogru_alanlarla_doner(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, price='250.00')
    response = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '2', 'unit_price': '250.00'},
    ])
    assert response.status_code == 201, response.text

    orders_response = client.get(f"/api/customers/{customer['id']}/orders")
    assert orders_response.status_code == 200
    orders = orders_response.json()
    assert len(orders) == 1
    order = orders[0]
    assert order['product'] == product['name']
    assert Decimal(str(order['amount'])) == Decimal('500.00')
    assert order['status'] == 'pending'
    assert order['order_date'] is not None


def test_orders_coklu_kalemli_sipariste_urun_ozeti_gosterir(client, tracker):
    customer = make_customer(client, tracker)
    product_a = make_product(client, tracker, price='100.00')
    product_b = make_product(client, tracker, price='50.00')
    response = make_sale(client, tracker, customer['id'], [
        {'product_id': product_a['id'], 'quantity': '1', 'unit_price': '100.00'},
        {'product_id': product_b['id'], 'quantity': '1', 'unit_price': '50.00'},
    ])
    assert response.status_code == 201, response.text

    orders = client.get(f"/api/customers/{customer['id']}/orders").json()
    assert len(orders) == 1
    assert '(+1 urun)' in orders[0]['product']
    assert Decimal(str(orders[0]['amount'])) == Decimal('150.00')


def test_orders_status_filtresi(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker)
    make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'},
    ])

    pending = client.get(f"/api/customers/{customer['id']}/orders", params={'status': 'pending'})
    assert len(pending.json()) == 1

    delivered = client.get(f"/api/customers/{customer['id']}/orders", params={'status': 'delivered'})
    assert delivered.json() == []


def test_orders_baska_musterinin_siparisini_gostermez(client, tracker):
    customer_a = make_customer(client, tracker, name='Musteri A')
    customer_b = make_customer(client, tracker, name='Musteri B')
    product = make_product(client, tracker)
    make_sale(client, tracker, customer_a['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'},
    ])

    orders_b = client.get(f"/api/customers/{customer_b['id']}/orders")
    assert orders_b.json() == []


def test_orders_iptal_edilen_siparis_listede_gorunmez(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker)
    created = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'},
    ])
    sale_id = created.json()['id']
    cancel_response = client.post(f'/api/sales/{sale_id}/cancel')
    assert cancel_response.status_code == 200, cancel_response.text

    orders = client.get(f"/api/customers/{customer['id']}/orders")
    assert orders.json() == []


def test_orders_siparissiz_musteri_bos_liste_doner(client, tracker):
    customer = make_customer(client, tracker)
    orders = client.get(f"/api/customers/{customer['id']}/orders")
    assert orders.status_code == 200
    assert orders.json() == []


def test_sales_trend_aylik_musteriye_ozel_ve_12_ay_doner(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker)
    make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '300.00'},
    ])

    trend = client.get(f"/api/customers/{customer['id']}/sales-trend", params={'range': 'monthly'})
    assert trend.status_code == 200
    data = trend.json()
    assert len(data) == 12
    this_month_total = sum(Decimal(str(m['sales'])) for m in data)
    assert this_month_total == Decimal('300.00')


def test_orders_authsiz_istek_401():
    anon_client = TestClient(app)
    response = anon_client.get('/api/customers/1/orders')
    assert response.status_code == 401
