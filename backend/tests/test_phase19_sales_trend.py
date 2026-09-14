"""Phase 19: Dashboard genel endpoint'leri (/api/sales/trend, /recent, /recent-orders)
- GERCEK sales_orders verisi.

Bu endpoint'ler tenant genelinde calistigi icin (tek musteri/urune filtreli
degil) diger testlerin veya ayni tenant'taki baska kayitlarin sayisina
bagimli kesin sayilar yerine yapi + "yeni olusturdugumuz kayit gorunuyor mu"
seklinde dogrulama yapilir.
"""
from decimal import Decimal

from tests.test_phase10_stock import make_customer, make_product, make_sale


def test_trend_4_mod_gecerli_yapi_doner(client):
    monthly = client.get('/api/sales/trend', params={'range': 'monthly'})
    assert monthly.status_code == 200
    assert len(monthly.json()) == 12

    yearly = client.get('/api/sales/trend', params={'range': 'yearly'})
    assert yearly.status_code == 200
    assert isinstance(yearly.json(), list)

    daily = client.get('/api/sales/trend', params={'range': 'daily'})
    assert daily.status_code == 200
    assert len(daily.json()) >= 28  # ayin gun sayisi (28-31)

    weekly = client.get('/api/sales/trend', params={'range': 'weekly'})
    assert weekly.status_code == 200
    assert 4 <= len(weekly.json()) <= 5


def test_trend_yeni_siparis_aylik_toplama_yansir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker)
    make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '999.00'},
    ])

    monthly = client.get('/api/sales/trend', params={'range': 'monthly'}).json()
    total_this_year = sum(Decimal(str(m['sales'])) for m in monthly)
    assert total_this_year >= Decimal('999.00')


def test_recent_sales_sayfalama_yapisi_dogru(client):
    response = client.get('/api/sales/recent', params={'page': 1, 'per_page': 5})
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {'rows', 'total', 'total_pages', 'page'}
    assert len(data['rows']) <= 5
    assert data['page'] == 1


def test_recent_sales_yeni_siparis_ilk_sayfada_gorunur(client, tracker):
    customer = make_customer(client, tracker, name='Recent Sales Test Musterisi')
    product = make_product(client, tracker)
    make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'},
    ])

    recent = client.get('/api/sales/recent', params={'page': 1, 'per_page': 50}).json()
    assert any(row['customer'] == customer['name'] for row in recent['rows'])


def test_recent_orders_yeni_siparis_listede_gorunur(client, tracker):
    customer = make_customer(client, tracker, name='Recent Orders Test Musterisi')
    product = make_product(client, tracker)
    make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'},
    ])

    orders = client.get('/api/sales/recent-orders').json()
    assert isinstance(orders, list)
    assert any(row['customer'] == customer['name'] for row in orders)
