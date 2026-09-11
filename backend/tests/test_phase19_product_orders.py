"""Phase 19: urun detay modal'i endpoint'leri - GERCEK sales_order_items verisi.

customer_orders testleriyle ayni desen; tek fark satirlarin kalem (item)
bazinda olmasi - coklu urunlu bir sipariste sadece ilgili urunun kalemi doner.
"""
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from tests.test_phase10_stock import make_customer, make_product, make_sale


def test_orders_gercek_kalemi_dogru_alanlarla_doner(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, price='75.00')
    response = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '3', 'unit_price': '75.00'},
    ])
    assert response.status_code == 201, response.text

    orders = client.get(f"/api/products/{product['id']}/orders").json()
    assert len(orders) == 1
    assert orders[0]['customer'] == customer['name']
    assert Decimal(str(orders[0]['amount'])) == Decimal('225.00')
    assert orders[0]['status'] == 'pending'


def test_orders_coklu_urunlu_sipariste_sadece_ilgili_kalem_doner(client, tracker):
    customer = make_customer(client, tracker)
    product_a = make_product(client, tracker, price='100.00')
    product_b = make_product(client, tracker, price='20.00')
    make_sale(client, tracker, customer['id'], [
        {'product_id': product_a['id'], 'quantity': '1', 'unit_price': '100.00'},
        {'product_id': product_b['id'], 'quantity': '1', 'unit_price': '20.00'},
    ])

    orders_a = client.get(f"/api/products/{product_a['id']}/orders").json()
    orders_b = client.get(f"/api/products/{product_b['id']}/orders").json()
    assert len(orders_a) == 1 and Decimal(str(orders_a[0]['amount'])) == Decimal('100.00')
    assert len(orders_b) == 1 and Decimal(str(orders_b[0]['amount'])) == Decimal('20.00')


def test_orders_status_filtresi(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker)
    make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'},
    ])

    pending = client.get(f"/api/products/{product['id']}/orders", params={'status': 'pending'})
    assert len(pending.json()) == 1
    delivered = client.get(f"/api/products/{product['id']}/orders", params={'status': 'delivered'})
    assert delivered.json() == []


def test_orders_satissiz_urun_bos_liste_doner(client, tracker):
    product = make_product(client, tracker)
    orders = client.get(f"/api/products/{product['id']}/orders")
    assert orders.status_code == 200
    assert orders.json() == []


def test_sales_trend_aylik_urune_ozel(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker)
    make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '2', 'unit_price': '60.00'},
    ])

    trend = client.get(f"/api/products/{product['id']}/sales-trend", params={'range': 'monthly'})
    assert trend.status_code == 200
    data = trend.json()
    assert len(data) == 12
    this_month_total = sum(Decimal(str(m['sales'])) for m in data)
    assert this_month_total == Decimal('120.00')


def test_orders_authsiz_istek_401():
    anon_client = TestClient(app)
    response = anon_client.get('/api/products/1/orders')
    assert response.status_code == 401
