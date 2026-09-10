"""Phase 15 testleri: satis zinciri refactoring (Quotation -> SalesOrder ->
DeliveryNote -> Invoice) ve kredi limiti.

Bu faz REFACTOR oldugu icin bazi testler data-migration'in gecmis veriyi
dogru tasidigini da dogrular (bkz. "8. Data migration validation" bolumu).
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text

from tests.conftest import admin_connection, unique_suffix
from tests.test_phase10_stock import make_customer, make_product, stock_of
from tests.test_phase12_tenant import superadmin_client, two_tenants  # noqa: F401
from tests.test_phase13_product import make_conversion, uoms  # noqa: F401


# ---------------- Yardimcilar ----------------

def make_quotation(client, tracker, customer_id, items, save_as_draft=False):
    response = client.post('/api/quotations', json={
        'customer_id': customer_id,
        'items': items,
        'save_as_draft': save_as_draft,
    })
    assert response.status_code == 201, response.text
    quotation = response.json()
    tracker.add('quotations', quotation['id'])
    return quotation


def make_sales_order(client, tracker, customer_id, items, save_as_draft=False, **extra):
    body = {
        'customer_id': customer_id,
        'items': items,
        'save_as_draft': save_as_draft,
    }
    body.update(extra)
    response = client.post('/api/sales-orders', json=body)
    if response.status_code == 201:
        tracker.add('sales', response.json()['id'])
    return response


def make_delivery_note(client, tracker, customer_id, items, sales_order_id=None,
                        save_as_draft=False, warehouse_id=None):
    body = {
        'customer_id': customer_id,
        'items': items,
        'save_as_draft': save_as_draft,
    }
    if sales_order_id is not None:
        body['sales_order_id'] = sales_order_id
    if warehouse_id is not None:
        body['warehouse_id'] = warehouse_id
    response = client.post('/api/delivery-notes', json=body)
    if response.status_code == 201:
        tracker.add('delivery_notes', response.json()['id'])
    return response


def make_invoice_v2(client, tracker, customer_id, items, **extra):
    body = {
        'customer_id': customer_id,
        'invoice_number': f'INV-{unique_suffix()}'[:50],
        'items': items,
    }
    body.update(extra)
    response = client.post('/api/invoices', json=body)
    if response.status_code == 201:
        tracker.add('invoices', response.json()['id'])
    return response


def set_credit(client, customer_id, limit, days=0):
    response = client.put(f'/api/customers/{customer_id}', json={
        'credit_limit': str(limit), 'credit_days': days,
    })
    assert response.status_code == 200, response.text
    return response.json()


def ledger_entries(client, product_id, reason=None, ref_type=None):
    params = {'product_id': product_id}
    if reason is not None:
        params['reason'] = reason
    response = client.get('/api/stock/ledger', params=params)
    assert response.status_code == 200, response.text
    rows = response.json()
    if ref_type is not None:
        rows = [r for r in rows if r['ref_type'] == ref_type]
    return rows


# ---------------- 1. Teklif (Quotation) ----------------

def test_teklif_olusturulup_gonderiliyor(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')

    quotation = make_quotation(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '5', 'unit_price': '20.00',
         'tax_rate': '10'},
    ])
    assert quotation['docstatus'] == 1
    assert quotation['quotation_number'].startswith('QT-'), quotation['quotation_number']
    assert quotation['status'] == 'gonderildi'
    assert Decimal(str(quotation['subtotal'])) == Decimal('100.00')
    assert Decimal(str(quotation['tax_total'])) == Decimal('10.00')
    assert Decimal(str(quotation['total_amount'])) == Decimal('110.00')


def test_teklif_taslak_kalabilir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    quotation = make_quotation(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '5.00'},
    ], save_as_draft=True)
    assert quotation['docstatus'] == 0
    assert quotation['status'] == 'taslak'
    assert quotation['quotation_number'] is None


def test_teklif_kabul_edilip_reddedilebilir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    quotation = make_quotation(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '5.00'},
    ])
    accepted = client.post(f'/api/quotations/{quotation["id"]}/accept')
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'kabul'

    other = make_quotation(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '5.00'},
    ])
    rejected = client.post(f'/api/quotations/{other["id"]}/reject')
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()['status'] == 'red'


def test_taslak_teklif_kabul_edilemez(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    quotation = make_quotation(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '5.00'},
    ], save_as_draft=True)
    response = client.post(f'/api/quotations/{quotation["id"]}/accept')
    assert response.status_code == 400, response.text


# ---------------- 2. Tekliften SalesOrder ----------------

def test_kabul_edilen_teklif_siparise_cevrilir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    quotation = make_quotation(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '3', 'unit_price': '15.00'},
    ])
    client.post(f'/api/quotations/{quotation["id"]}/accept')

    response = client.post(
        f'/api/quotations/{quotation["id"]}/to-sales-order', json={}
    )
    assert response.status_code == 201, response.text
    order = response.json()
    tracker.add('sales', order['id'])
    assert order['quotation_id'] == quotation['id']
    assert order['docstatus'] == 1
    assert order['so_number'].startswith('SO-'), order['so_number']
    assert Decimal(str(order['total_amount'])) == Decimal('45.00')
    # Stok hareketi olusmadi - siparis niyet beyanidir
    assert stock_of(client, product['id']) == Decimal('0')


def test_kabul_edilmemis_teklif_siparise_cevrilemez(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    quotation = make_quotation(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '5.00'},
    ])
    response = client.post(
        f'/api/quotations/{quotation["id"]}/to-sales-order', json={}
    )
    assert response.status_code == 400, response.text


def test_teklifsiz_siparis_dogrudan_acilabilir(client, tracker):
    """Opsiyonel akis: Quotation atlanip dogrudan SalesOrder acilabilir."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    response = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '2', 'unit_price': '30.00'},
    ])
    assert response.status_code == 201, response.text
    order = response.json()
    assert order['quotation_id'] is None
    assert order['so_number'].startswith('SO-')


# ---------------- 3. SalesOrder onayi stok hareketi yaratmaz ----------------

def test_siparis_onayi_stogu_degistirmez(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    before = stock_of(client, product['id'])

    response = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '5', 'unit_price': '10.00'},
    ])
    assert response.status_code == 201, response.text
    assert stock_of(client, product['id']) == before
    assert ledger_entries(client, product['id'], ref_type='delivery') == []


def test_onaylanmis_siparis_duzenlenemez(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '5.00'},
    ]).json()
    response = client.put(f'/api/sales-orders/{order["id"]}', json={
        'customer_id': customer['id'],
        'items': [{'product_id': product['id'], 'quantity': '2', 'unit_price': '5.00'}],
    })
    assert response.status_code == 400, response.text


# ---------------- 4. DeliveryNote onayi stok dusurur ----------------

def test_sevkiyat_onayi_stogu_dusurur(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='20')
    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '8', 'unit_price': '5.00'},
    ]).json()
    order_item = order['items'][0]

    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'sales_order_item_id': order_item['id'],
        'quantity': '8', 'unit_price': '5.00',
    }], sales_order_id=order['id'])
    assert dn.status_code == 201, dn.text
    body = dn.json()
    assert body['docstatus'] == 1
    assert body['delivery_note_number'].startswith('IR-'), body['delivery_note_number']

    assert stock_of(client, product['id']) == Decimal('12')
    entries = ledger_entries(client, product['id'], reason='satis', ref_type='delivery')
    assert len(entries) == 1
    assert Decimal(str(entries[0]['change_qty'])) == Decimal('-8')
    assert entries[0]['ref_id'] == body['id']

    refreshed = client.get(f'/api/sales-orders/{order["id"]}').json()
    assert refreshed['status'] == 'delivered'
    assert Decimal(str(refreshed['items'][0]['delivered_quantity'])) == Decimal('8')


def test_siparissiz_sevkiyat_yapilabilir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'quantity': '4', 'unit_price': '5.00',
    }])
    assert dn.status_code == 201, dn.text
    assert dn.json()['sales_order_id'] is None
    assert stock_of(client, product['id']) == Decimal('6')


# ---------------- 5. Kismi sevkiyat ----------------

def test_kismi_sevkiyat_siparisi_kismi_teslime_cevirir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='100')
    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '100', 'unit_price': '2.00'},
    ]).json()
    order_item = order['items'][0]

    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'sales_order_item_id': order_item['id'],
        'quantity': '60', 'unit_price': '2.00',
    }], sales_order_id=order['id'])
    assert dn.status_code == 201, dn.text

    refreshed = client.get(f'/api/sales-orders/{order["id"]}').json()
    assert refreshed['status'] == 'partially_delivered'
    item = refreshed['items'][0]
    assert Decimal(str(item['delivered_quantity'])) == Decimal('60')
    assert Decimal(str(item['remaining_quantity'])) == Decimal('40')


def test_siparisten_getir_kalan_miktari_doner(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='50')
    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '50', 'unit_price': '1.00'},
    ]).json()
    order_item = order['items'][0]
    make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'sales_order_item_id': order_item['id'],
        'quantity': '20', 'unit_price': '1.00',
    }], sales_order_id=order['id'])

    draft = client.get(f'/api/delivery-notes/from-order/{order["id"]}')
    assert draft.status_code == 200, draft.text
    items = draft.json()['items']
    assert len(items) == 1
    assert Decimal(str(items[0]['quantity'])) == Decimal('30')


# ---------------- 6. Fazla sevkiyat engellenir ----------------

def test_fazla_sevkiyat_400_doner(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '10', 'unit_price': '1.00'},
    ]).json()
    order_item = order['items'][0]

    response = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'sales_order_item_id': order_item['id'],
        'quantity': '15', 'unit_price': '1.00',
    }], sales_order_id=order['id'])
    assert response.status_code == 400, response.text
    assert 'fazla sevkiyat' in response.json()['detail']


# ---------------- 7. Sevkiyat iptali stogu geri verir ----------------

def test_sevkiyat_iptali_stogu_geri_verir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='30')
    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '30', 'unit_price': '4.00'},
    ]).json()
    order_item = order['items'][0]

    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'sales_order_item_id': order_item['id'],
        'quantity': '30', 'unit_price': '4.00',
    }], sales_order_id=order['id'])
    assert dn.status_code == 201, dn.text
    assert stock_of(client, product['id']) == Decimal('0')

    cancelled = client.post(f'/api/delivery-notes/{dn.json()["id"]}/cancel',
                            json={'reason': 'Hasarli teslimat'})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()['docstatus'] == 2

    assert stock_of(client, product['id']) == Decimal('30')
    iade = ledger_entries(client, product['id'], reason='satis_iptal')
    assert len(iade) == 1
    assert Decimal(str(iade[0]['change_qty'])) == Decimal('30')

    refreshed = client.get(f'/api/sales-orders/{order["id"]}').json()
    assert refreshed['status'] == 'confirmed'
    assert Decimal(str(refreshed['items'][0]['delivered_quantity'])) == Decimal('0')


def test_onaylanmis_sevkiyat_duzenlenemez(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='5')
    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'quantity': '5', 'unit_price': '1.00',
    }])
    assert dn.status_code == 201, dn.text
    assert client.delete(f'/api/delivery-notes/{dn.json()["id"]}').status_code == 400


# ---------------- 8. Koli/adet donusumu (Phase 13 entegrasyonu) ----------------

def test_koli_siparis_adet_stok_dususu(client, tracker, uoms):
    suffix = unique_suffix()
    created = client.post('/api/products', json={
        'name': f'Koli Satis {suffix}', 'sku': f'P15-{suffix}', 'price': '96.00',
        'stock_uom_id': uoms['adet'], 'sales_uom_id': uoms['koli'], 'stock': '100',
    })
    assert created.status_code == 201, created.text
    product = created.json()
    tracker.add('products', product['id'])
    make_conversion(client, tracker, uoms['koli'], uoms['adet'], '12', product['id'])

    customer = make_customer(client, tracker)
    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'uom_id': uoms['koli'],
         'quantity': '5', 'unit_price': '96.00'},
    ]).json()
    order_item = order['items'][0]
    assert order_item['uom_id'] == uoms['koli']
    assert Decimal(str(order_item['stock_quantity'])) == Decimal('60')

    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'sales_order_item_id': order_item['id'],
        'uom_id': uoms['koli'], 'quantity': '5', 'unit_price': '96.00',
    }], sales_order_id=order['id'])
    assert dn.status_code == 201, dn.text
    assert Decimal(str(dn.json()['items'][0]['stock_quantity'])) == Decimal('60')

    assert stock_of(client, product['id']) == Decimal('40')
    entries = ledger_entries(client, product['id'], reason='satis', ref_type='delivery')
    assert Decimal(str(entries[0]['change_qty'])) == Decimal('-60')


# ---------------- 9. Fatura mali belgedir, stok degistirmez ----------------

def test_kalemli_fatura_stogu_degistirmez(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'quantity': '10', 'unit_price': '7.50',
    }])
    assert dn.status_code == 201, dn.text
    before = stock_of(client, product['id'])

    invoice = make_invoice_v2(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '10', 'unit_price': '7.50',
         'tax_rate': '20'},
    ], delivery_note_id=dn.json()['id'])
    assert invoice.status_code == 201, invoice.text
    body = invoice.json()
    assert Decimal(str(body['subtotal'])) == Decimal('75.00')
    assert Decimal(str(body['tax_total'])) == Decimal('15.00')
    assert Decimal(str(body['total_amount'])) == Decimal('90.00')
    assert body['delivery_note_id'] == dn.json()['id']
    assert stock_of(client, product['id']) == before


def test_sevkiyattan_fatura_taslagi_cikarilir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='3')
    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'quantity': '3', 'unit_price': '12.00',
    }])
    assert dn.status_code == 201, dn.text

    draft = client.get(f'/api/delivery-notes/{dn.json()["id"]}/invoice-draft')
    assert draft.status_code == 200, draft.text
    items = draft.json()['items']
    assert len(items) == 1
    assert Decimal(str(items[0]['quantity'])) == Decimal('3')


def test_uyum_katmani_faturasi_stogu_degistirmez(client, tracker):
    """Eski /api/sales/{id}/invoice akisi hala calisiyor mu (geriye uyum)."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = client.post('/api/sales', json={
        'customer_id': customer['id'],
        'items': [{'product_id': product['id'], 'quantity': 2, 'unit_price': '25.00'}],
    })
    assert sale.status_code == 201, sale.text
    sale = sale.json()
    tracker.add('sales', sale['id'])
    before = stock_of(client, product['id'])

    invoice = client.post(f'/api/sales/{sale["id"]}/invoice', json={'tax_rate': '0.20'})
    assert invoice.status_code == 201, invoice.text
    tracker.add('invoices', invoice.json()['id'])
    assert stock_of(client, product['id']) == before
    assert Decimal(str(invoice.json()['total_amount'])) == Decimal('60.00')


# ---------------- 10. due_date credit_days'ten hesaplanir ----------------

def test_fatura_vadesi_musteri_vade_gununden_hesaplanir(client, tracker):
    customer = make_customer(client, tracker)
    set_credit(client, customer['id'], limit='0', days=30)
    product = make_product(client, tracker, stock='0')

    invoice = make_invoice_v2(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'},
    ], issued_date=date.today().isoformat())
    assert invoice.status_code == 201, invoice.text
    expected = (date.today() + timedelta(days=30)).isoformat()
    assert invoice.json()['due_date'] == expected


def test_taslak_fatura_vade_almaz(client, tracker):
    customer = make_customer(client, tracker)
    set_credit(client, customer['id'], limit='0', days=15)
    product = make_product(client, tracker, stock='0')

    invoice = make_invoice_v2(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'},
    ], save_as_draft=True)
    assert invoice.status_code == 201, invoice.text
    assert invoice.json()['due_date'] is None


# ---------------- 11. Kredi limiti ----------------

def test_limitsiz_musteride_uyari_yok(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1000', 'unit_price': '500.00'},
    ]).json()
    assert order.get('credit_warning') is None


def test_kredi_limiti_asiminda_uyari_doner(client, tracker):
    customer = make_customer(client, tracker)
    set_credit(client, customer['id'], limit='100')
    product = make_product(client, tracker, stock='0')

    order = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '500.00'},
    ])
    assert order.status_code == 201, order.text
    body = order.json()
    assert body['docstatus'] == 1  # uyari engellemez, siparis yine onaylanir
    assert body['credit_warning'] is not None
    assert body['credit_warning']['allowed'] is False


def test_kredi_limiti_block_ile_reddedilir(client, tracker):
    customer = make_customer(client, tracker)
    set_credit(client, customer['id'], limit='50')
    product = make_product(client, tracker, stock='0')

    response = make_sales_order(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '500.00'},
    ], block_if_credit_exceeded=True)
    assert response.status_code == 400, response.text


def test_kredi_kullanimi_odenmemis_faturalardan_hesaplanir(client, tracker):
    customer = make_customer(client, tracker)
    set_credit(client, customer['id'], limit='1000')
    product = make_product(client, tracker, stock='0')

    invoice = make_invoice_v2(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '400.00'},
    ])
    assert invoice.status_code == 201, invoice.text

    summary = client.get(f'/api/credit/customers/{customer["id"]}')
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert Decimal(str(body['credit_used'])) == Decimal('400.00')
    assert Decimal(str(body['available'])) == Decimal('600.00')

    # Fatura odenince kullanim dusmeli
    paid = client.put(f'/api/invoices/{invoice.json()["id"]}/payment',
                      json={'payment_status': 'odendi'})
    assert paid.status_code == 200, paid.text
    summary2 = client.get(f'/api/credit/customers/{customer["id"]}').json()
    assert Decimal(str(summary2['credit_used'])) == Decimal('0')


# ---------------- 12. Tenant izolasyonu (Phase 12 entegrasyonu) ----------------

def test_teklif_ve_siparis_tenant_bazli_izole(two_tenants):
    a, b = two_tenants
    suffix = unique_suffix()
    customer = a.client.post('/api/customers', json={
        'name': f'A Musteri {suffix}', 'email': f'p15-a-{suffix}@erptest.com',
    })
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()['id']

    product = a.client.post('/api/products', json={
        'name': f'A Urun {suffix}', 'sku': f'P15A-{suffix}', 'price': '10.00',
        'stock': '5',
    })
    assert product.status_code == 201, product.text
    product_id = product.json()['id']

    order = a.client.post('/api/sales-orders', json={
        'customer_id': customer_id,
        'items': [{'product_id': product_id, 'quantity': '1', 'unit_price': '10.00'}],
    })
    assert order.status_code == 201, order.text
    order_id = order.json()['id']

    assert not any(o['id'] == order_id for o in b.client.get('/api/sales-orders').json())
    assert b.client.get(f'/api/sales-orders/{order_id}').status_code == 404


# ---------------- 13. Uctan uca ----------------

def test_uctan_uca_teklif_siparis_sevkiyat_fatura_stok_tutarli(client, tracker, uoms):
    """Teklif -> siparis -> sevkiyat -> fatura -> (uyum katmani) yeniden satis.

    Stok yalnizca sevkiyat/satis anlarinda hareket etmeli; siparis ve fatura
    dokunmamali. Yeni akis ile eski uyum katmaninin AYNI urun uzerinde
    dogru bilesim (composition) verdigi de dogrulanir.
    """
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='55')

    quotation = make_quotation(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '40', 'unit_price': '10.00'},
    ])
    client.post(f'/api/quotations/{quotation["id"]}/accept')
    order = client.post(
        f'/api/quotations/{quotation["id"]}/to-sales-order', json={}
    ).json()
    tracker.add('sales', order['id'])
    # Siparis niyet beyanidir - stok hareketi olusmadi
    assert stock_of(client, product['id']) == Decimal('55')

    order_item = order['items'][0]
    dn = make_delivery_note(client, tracker, customer['id'], [{
        'product_id': product['id'], 'sales_order_item_id': order_item['id'],
        'quantity': '40', 'unit_price': '10.00',
    }], sales_order_id=order['id'])
    assert dn.status_code == 201, dn.text
    assert stock_of(client, product['id']) == Decimal('15')

    invoice = make_invoice_v2(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': '40', 'unit_price': '10.00'},
    ], delivery_note_id=dn.json()['id'])
    assert invoice.status_code == 201, invoice.text
    # Fatura mali belgedir - stok hareketi yaratmaz
    assert stock_of(client, product['id']) == Decimal('15')

    # Kalan 15 adet, uyum katmani (/api/sales) uzerinden farkli bir musteriye
    # satiliyor - yeni ve eski akisin AYNI stok toplaminda dogru bilesmesi
    resale_customer = make_customer(client, tracker)
    resale = client.post('/api/sales', json={
        'customer_id': resale_customer['id'],
        'items': [{'product_id': product['id'], 'quantity': 15, 'unit_price': '18.00'}],
    })
    assert resale.status_code == 201, resale.text
    tracker.add('sales', resale.json()['id'])
    assert stock_of(client, product['id']) == Decimal('0')


# ---------------- 14. Data migration validation ----------------

def test_yeni_tablolar_tenant_bazli_ve_rls_altinda():
    with admin_connection() as conn:
        for table in ('quotations', 'quotation_items', 'delivery_notes',
                      'delivery_note_items', 'invoice_items',
                      'sales_orders', 'sales_order_items'):
            has_tenant = conn.execute(
                text(
                    'SELECT 1 FROM information_schema.columns '
                    "WHERE table_name = :t AND column_name = 'tenant_id'"
                ),
                {'t': table},
            ).first()
            assert has_tenant, f'{table}.tenant_id yok'

            enabled, forced = conn.execute(
                text(
                    'SELECT c.relrowsecurity, c.relforcerowsecurity '
                    'FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
                    "WHERE c.relname = :t AND n.nspname = 'public'"
                ),
                {'t': table},
            ).first()
            assert enabled and forced, f'{table}: RLS eksik'


def test_eski_ref_type_sale_kalintisi_yok():
    """Migration 'sale' -> 'delivery' remap'ini tamamlamis olmali."""
    with admin_connection() as conn:
        leftover = conn.execute(text(
            "SELECT count(*) FROM stock_ledger_entries "
            "WHERE reason IN ('satis', 'satis_iptal') AND ref_type = 'sale'"
        )).scalar()
    assert leftover == 0


def test_delivery_ref_id_her_zaman_bir_delivery_note_gosterir():
    with admin_connection() as conn:
        dangling = conn.execute(text(
            "SELECT count(*) FROM stock_ledger_entries sle "
            "WHERE sle.ref_type = 'delivery' "
            "  AND NOT EXISTS (SELECT 1 FROM delivery_notes dn WHERE dn.id = sle.ref_id)"
        )).scalar()
    assert dangling == 0


def test_eski_invoice_sale_id_hala_cozuluyor(client, tracker):
    """Eski Sale -> yeni SalesOrder gecisinde invoice.sale_id kirilmadi mi."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='5')
    sale = client.post('/api/sales', json={
        'customer_id': customer['id'],
        'items': [{'product_id': product['id'], 'quantity': 1, 'unit_price': '10.00'}],
    })
    assert sale.status_code == 201, sale.text
    sale = sale.json()
    tracker.add('sales', sale['id'])

    invoice = client.post(f'/api/sales/{sale["id"]}/invoice', json={})
    assert invoice.status_code == 201, invoice.text
    tracker.add('invoices', invoice.json()['id'])
    assert invoice.json()['sale_id'] == sale['id']

    # sale_id uzerinden hala satisin kendisi cozulebiliyor mu (SalesOrder)
    fetched = client.get(f'/api/sales-orders/{sale["id"]}')
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()['id'] == sale['id']


def test_migration_iki_kez_calisinca_bozulmaz():
    import migrate_phase15_sales

    migrate_phase15_sales.main()
    migrate_phase15_sales.main()

