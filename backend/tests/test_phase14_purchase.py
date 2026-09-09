"""Phase 14 testleri: tedarikci, satin alma siparisi, mal kabul ve alis faturasi.

Notion "Phase 14 - Adim 8" listesindeki her madde burada bir testtir
(RFQ / tedarikci teklifi maddeleri Phase 14.5'e ertelendi).
"""
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.conftest import admin_connection, unique_suffix
from tests.test_phase10_stock import make_customer, make_product, stock_of
from tests.test_phase12_tenant import superadmin_client, two_tenants  # noqa: F401
from tests.test_phase13_product import make_conversion, uoms  # noqa: F401


def make_supplier(client, tracker, payment_term_days=0):
    suffix = unique_suffix()
    response = client.post('/api/suppliers', json={
        'code': f'TED-{suffix}'[:50],
        'name': f'Tedarikci {suffix}',
        'tax_number': '1234567890',
        'payment_term_days': payment_term_days,
    })
    assert response.status_code == 201, response.text
    supplier = response.json()
    tracker.add('suppliers', supplier['id'])
    return supplier


def make_order(client, tracker, supplier, items, save_as_draft=False, expected_date=None):
    body = {
        'supplier_id': supplier['id'],
        'items': items,
        'save_as_draft': save_as_draft,
    }
    if expected_date is not None:
        body['expected_date'] = expected_date
    response = client.post('/api/purchase-orders', json=body)
    assert response.status_code == 201, response.text
    order = response.json()
    tracker.add('purchase_orders', order['id'])
    return order


def make_receipt(client, tracker, supplier, items, order=None, save_as_draft=False):
    body = {
        'supplier_id': supplier['id'],
        'items': items,
        'save_as_draft': save_as_draft,
    }
    if order is not None:
        body['purchase_order_id'] = order['id']
    response = client.post('/api/purchase-receipts', json=body)
    if response.status_code == 201:
        tracker.add('purchase_receipts', response.json()['id'])
    return response


def make_invoice(client, tracker, supplier, items, invoice_number=None, **extra):
    body = {
        'supplier_id': supplier['id'],
        'invoice_number': invoice_number or f'FT-{unique_suffix()}'[:50],
        'items': items,
    }
    body.update(extra)
    response = client.post('/api/purchase-invoices', json=body)
    if response.status_code == 201:
        tracker.add('purchase_invoices', response.json()['id'])
    return response


def ledger_entries(client, product_id, reason=None):
    params = {'product_id': product_id}
    if reason is not None:
        params['reason'] = reason
    response = client.get('/api/stock/ledger', params=params)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------- 1. Tedarikci ----------------

def test_tedarikci_crud(client, tracker):
    supplier = make_supplier(client, tracker, payment_term_days=30)
    assert supplier['payment_term_days'] == 30
    assert supplier['is_active'] is True

    response = client.put(f'/api/suppliers/{supplier["id"]}',
                          json={'city': 'Istanbul', 'contact_person': 'Ayse Yilmaz'})
    assert response.status_code == 200, response.text
    assert response.json()['city'] == 'Istanbul'

    listed = client.get('/api/suppliers').json()
    assert any(s['id'] == supplier['id'] for s in listed)

    detail = client.get(f'/api/suppliers/{supplier["id"]}').json()
    assert detail['contact_person'] == 'Ayse Yilmaz'


def test_vkn_uzunlugu_dogrulaniyor(client, tracker):
    suffix = unique_suffix()
    response = client.post('/api/suppliers', json={
        'code': f'TED-{suffix}'[:50], 'name': 'Hatali VKN', 'tax_number': '12345'})
    assert response.status_code == 422, response.text


def test_satinalma_kaydi_olan_tedarikci_silinemez(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '10', 'unit_price': '5.00'}])

    response = client.delete(f'/api/suppliers/{supplier["id"]}')
    assert response.status_code == 400, response.text
    assert 'silinemez' in response.json()['detail']


def test_satinalma_kaydi_olmayan_tedarikci_silinebilir(client, tracker):
    suffix = unique_suffix()
    created = client.post('/api/suppliers', json={
        'code': f'TED-{suffix}'[:50], 'name': f'Gecici {suffix}'})
    assert created.status_code == 201, created.text
    assert client.delete(f'/api/suppliers/{created.json()["id"]}').status_code == 204


# ---------------- 2. Satin alma siparisi ----------------

def test_siparis_olusturulup_onaylanabiliyor(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')

    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '10', 'unit_price': '25.00',
         'tax_rate': '20'}])

    assert order['docstatus'] == 1
    assert order['po_number'].startswith('SAS-'), order['po_number']
    assert order['status'] == 'beklemede'
    assert Decimal(str(order['subtotal'])) == Decimal('250.00')
    assert Decimal(str(order['tax_total'])) == Decimal('50.00')
    assert Decimal(str(order['grand_total'])) == Decimal('300.00')
    assert Decimal(str(order['items'][0]['remaining_quantity'])) == Decimal('10')


def test_siparis_tutarlari_backendde_hesaplaniyor(client, tracker, uoms):
    """Frontend'den gelen toplama guvenilmez; hesap kalemlerden yapilir."""
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '3', 'unit_price': '19.99',
         'tax_rate': '10'}])
    assert Decimal(str(order['subtotal'])) == Decimal('59.97')
    assert Decimal(str(order['tax_total'])) == Decimal('6.00')


def test_siparis_onayi_stogu_degistirmez(client, tracker, uoms):
    """Siparis niyet beyanidir - ledger'a dokunmaz."""
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='7')
    before = stock_of(client, product['id'])

    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '100', 'unit_price': '5.00'}],
        save_as_draft=True)
    assert stock_of(client, product['id']) == before

    submitted = client.post(f'/api/purchase-orders/{order["id"]}/submit')
    assert submitted.status_code == 200, submitted.text
    assert stock_of(client, product['id']) == before
    assert ledger_entries(client, product['id'], reason='alim') == []


def test_onaylanmis_siparis_duzenlenemez(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '5', 'unit_price': '1.00'}])

    response = client.put(f'/api/purchase-orders/{order["id"]}', json={'note': 'degisiklik'})
    assert response.status_code == 400, response.text


# ---------------- 3. Mal kabul ve stok ----------------

def test_mal_kabul_onayi_stogu_artirir(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '20', 'unit_price': '8.00'}])
    order_item = order['items'][0]

    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'],
        'purchase_order_item_id': order_item['id'],
        'quantity': '20', 'accepted_quantity': '20', 'unit_price': '8.00',
    }], order=order)
    assert receipt.status_code == 201, receipt.text
    body = receipt.json()
    assert body['docstatus'] == 1
    assert body['receipt_number'].startswith('MK-'), body['receipt_number']

    assert stock_of(client, product['id']) == Decimal('20')
    entries = ledger_entries(client, product['id'], reason='alim')
    assert len(entries) == 1
    assert Decimal(str(entries[0]['change_qty'])) == Decimal('20')
    assert entries[0]['ref_type'] == 'purchase'
    assert entries[0]['ref_id'] == body['id']

    refreshed = client.get(f'/api/purchase-orders/{order["id"]}').json()
    assert refreshed['status'] == 'tamamlandi'


def test_kismi_kabul_siparisi_kismi_teslime_cevirir(client, tracker, uoms):
    """100 siparis edilip 60 gelirse kalan 40 gorunmeli."""
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '100', 'unit_price': '2.00'}])
    order_item = order['items'][0]

    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'],
        'purchase_order_item_id': order_item['id'],
        'quantity': '60', 'accepted_quantity': '60', 'unit_price': '2.00',
    }], order=order)
    assert receipt.status_code == 201, receipt.text

    refreshed = client.get(f'/api/purchase-orders/{order["id"]}').json()
    assert refreshed['status'] == 'kismi_teslim'
    item = refreshed['items'][0]
    assert Decimal(str(item['received_quantity'])) == Decimal('60')
    assert Decimal(str(item['remaining_quantity'])) == Decimal('40')
    assert stock_of(client, product['id']) == Decimal('60')


def test_fazla_kabul_400_doner(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '10', 'unit_price': '1.00'}])
    order_item = order['items'][0]

    response = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'],
        'purchase_order_item_id': order_item['id'],
        'quantity': '15', 'accepted_quantity': '15', 'unit_price': '1.00',
    }], order=order)
    assert response.status_code == 400, response.text
    assert 'fazla kabul edilemez' in response.json()['detail']


def test_koli_kabul_ledgera_adet_duser(client, tracker, uoms):
    """Phase 13 entegrasyonu: 5 koli kabul edilirse ledger'a 60 adet yazilir."""
    suffix = unique_suffix()
    created = client.post('/api/products', json={
        'name': f'Koli Alim {suffix}',
        'sku': f'P14-{suffix}',
        'price': '10.00',
        'stock_uom_id': uoms['adet'],
        'purchase_uom_id': uoms['koli'],
        'stock': '0',
    })
    assert created.status_code == 201, created.text
    product = created.json()
    tracker.add('products', product['id'])
    make_conversion(client, tracker, uoms['koli'], uoms['adet'], '12', product['id'])

    supplier = make_supplier(client, tracker)
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'uom_id': uoms['koli'],
         'quantity': '5', 'unit_price': '96.00'}])
    order_item = order['items'][0]
    assert order_item['uom_id'] == uoms['koli']

    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'],
        'purchase_order_item_id': order_item['id'],
        'uom_id': uoms['koli'],
        'quantity': '5', 'accepted_quantity': '5', 'unit_price': '96.00',
    }], order=order)
    assert receipt.status_code == 201, receipt.text

    assert stock_of(client, product['id']) == Decimal('60')
    entries = ledger_entries(client, product['id'], reason='alim')
    assert Decimal(str(entries[0]['change_qty'])) == Decimal('60')

    item = receipt.json()['items'][0]
    assert Decimal(str(item['accepted_quantity'])) == Decimal('5')
    assert Decimal(str(item['stock_quantity'])) == Decimal('60')


def test_mal_kabul_iptali_stogu_geri_alir(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '30', 'unit_price': '4.00'}])
    order_item = order['items'][0]

    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'],
        'purchase_order_item_id': order_item['id'],
        'quantity': '30', 'accepted_quantity': '30', 'unit_price': '4.00',
    }], order=order)
    assert receipt.status_code == 201, receipt.text
    assert stock_of(client, product['id']) == Decimal('30')

    cancelled = client.post(f'/api/purchase-receipts/{receipt.json()["id"]}/cancel',
                            json={'reason': 'Hatali sevkiyat'})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()['docstatus'] == 2

    assert stock_of(client, product['id']) == Decimal('0')
    iade = ledger_entries(client, product['id'], reason='alim_iade')
    assert len(iade) == 1
    assert Decimal(str(iade[0]['change_qty'])) == Decimal('-30')

    refreshed = client.get(f'/api/purchase-orders/{order["id"]}').json()
    assert refreshed['status'] == 'beklemede'
    assert Decimal(str(refreshed['items'][0]['received_quantity'])) == Decimal('0')


def test_onaylanmis_mal_kabul_duzenlenemez(client, tracker, uoms):
    """Phase 11 entegrasyonu: onayli belge kilitlidir."""
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'], 'quantity': '5',
        'accepted_quantity': '5', 'unit_price': '3.00',
    }])
    assert receipt.status_code == 201, receipt.text
    assert client.delete(
        f'/api/purchase-receipts/{receipt.json()["id"]}').status_code == 400


def test_siparissiz_mal_kabul_yapilabilir(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'], 'quantity': '12',
        'accepted_quantity': '12', 'unit_price': '2.50',
    }])
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()['purchase_order_id'] is None
    assert stock_of(client, product['id']) == Decimal('12')


def test_kismi_red_yalnizca_kabulu_stoga_yazar(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'], 'quantity': '10',
        'accepted_quantity': '7', 'rejected_quantity': '3',
        'unit_price': '5.00', 'reject_reason': 'Ambalaj hasarli',
    }])
    assert receipt.status_code == 201, receipt.text
    assert stock_of(client, product['id']) == Decimal('7')


def test_siparisten_getir_kalan_miktarlari_doner(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '50', 'unit_price': '1.00'}])
    order_item = order['items'][0]

    make_receipt(client, tracker, supplier, [{
        'product_id': product['id'],
        'purchase_order_item_id': order_item['id'],
        'quantity': '20', 'accepted_quantity': '20', 'unit_price': '1.00',
    }], order=order)

    draft = client.get(f'/api/purchase-receipts/from-order/{order["id"]}')
    assert draft.status_code == 200, draft.text
    body = draft.json()
    assert len(body['items']) == 1
    assert Decimal(str(body['items'][0]['quantity'])) == Decimal('30')


# ---------------- 4. Alis faturasi ----------------

def test_alis_faturasi_stogu_degistirmez(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'], 'quantity': '10',
        'accepted_quantity': '10', 'unit_price': '6.00',
    }])
    assert receipt.status_code == 201, receipt.text
    before = stock_of(client, product['id'])

    invoice = make_invoice(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '10', 'unit_price': '6.00'}],
        purchase_receipt_id=receipt.json()['id'])
    assert invoice.status_code == 201, invoice.text
    assert invoice.json()['internal_number'].startswith('AF-')
    assert stock_of(client, product['id']) == before


def test_ayni_tedarikciden_ayni_fatura_no_ikinci_kez_girilemez(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    number = f'AYNI-{unique_suffix()}'[:50]
    items = [{'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'}]

    first = make_invoice(client, tracker, supplier, items, invoice_number=number)
    assert first.status_code == 201, first.text

    second = make_invoice(client, tracker, supplier, items, invoice_number=number)
    assert second.status_code == 409, second.text


def test_fatura_vadesi_odeme_gununden_hesaplanir(client, tracker, uoms):
    from datetime import date, timedelta

    supplier = make_supplier(client, tracker, payment_term_days=45)
    product = make_product(client, tracker, stock='0')
    invoice = make_invoice(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '1', 'unit_price': '10.00'}],
        invoice_date=date.today().isoformat())
    assert invoice.status_code == 201, invoice.text
    expected = (date.today() + timedelta(days=45)).isoformat()
    assert invoice.json()['due_date'] == expected


# ---------------- 5. Uclu eslestirme ----------------

def test_uclu_eslestirme_farklari_gosterir(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '100', 'unit_price': '10.00'}])
    order_item = order['items'][0]

    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'],
        'purchase_order_item_id': order_item['id'],
        'quantity': '60', 'accepted_quantity': '60', 'unit_price': '10.00',
    }], order=order)
    assert receipt.status_code == 201, receipt.text

    invoice = make_invoice(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '60', 'unit_price': '12.00'}],
        purchase_receipt_id=receipt.json()['id'])
    assert invoice.status_code == 201, invoice.text

    match = client.get(f'/api/purchase/match/{order["id"]}')
    assert match.status_code == 200, match.text
    body = match.json()
    assert body['has_difference'] is True
    row = body['rows'][0]
    assert Decimal(str(row['ordered_quantity'])) == Decimal('100')
    assert Decimal(str(row['received_quantity'])) == Decimal('60')
    assert Decimal(str(row['invoiced_quantity'])) == Decimal('60')
    assert Decimal(str(row['invoice_unit_price'])) == Decimal('12.00')
    assert row['quantity_difference'] is True
    assert row['price_difference'] is True


# ---------------- 6. Raporlar ----------------

def test_bekleyen_siparis_raporu(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '5', 'unit_price': '1.00'}],
        expected_date='2020-01-01')

    response = client.get('/api/reports/pending-purchase-orders')
    assert response.status_code == 200, response.text
    rows = {r['id']: r for r in response.json()}
    assert order['id'] in rows
    assert rows[order['id']]['is_overdue'] is True


def test_tedarikci_performans_raporu(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'], 'quantity': '10',
        'accepted_quantity': '8', 'rejected_quantity': '2', 'unit_price': '5.00',
    }])
    assert receipt.status_code == 201, receipt.text

    response = client.get('/api/reports/supplier-performance')
    assert response.status_code == 200, response.text
    rows = {r['supplier_id']: r for r in response.json()}
    assert supplier['id'] in rows
    assert Decimal(str(rows[supplier['id']]['reject_rate'])) == Decimal('20.00')


def test_urun_alim_fiyat_gecmisi(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    make_receipt(client, tracker, supplier, [{
        'product_id': product['id'], 'quantity': '4',
        'accepted_quantity': '4', 'unit_price': '17.50',
    }])

    response = client.get('/api/reports/product-purchase-history',
                          params={'product_id': product['id']})
    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows and Decimal(str(rows[0]['unit_price'])) == Decimal('17.50')


# ---------------- 7. Semasal kontroller ----------------

def test_yeni_tablolar_tenant_bazli_ve_rls_altinda():
    from migrate_phase14_purchase import NEW_TABLES

    with admin_connection() as conn:
        for table in NEW_TABLES:
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


def test_ledgerda_birim_maliyet_alani_var():
    with admin_connection() as conn:
        found = conn.execute(text(
            'SELECT 1 FROM information_schema.columns '
            "WHERE table_name = 'stock_ledger_entries' AND column_name = 'unit_cost'"
        )).first()
    assert found, 'stock_ledger_entries.unit_cost yok'


def test_mal_kabul_ledgera_birim_maliyet_yazar(client, tracker, uoms):
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')
    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'], 'quantity': '10',
        'accepted_quantity': '10', 'unit_price': '13.25',
    }])
    assert receipt.status_code == 201, receipt.text

    with admin_connection() as conn:
        cost = conn.execute(
            text(
                'SELECT unit_cost FROM stock_ledger_entries '
                "WHERE ref_type = 'purchase' AND ref_id = :r"
            ),
            {'r': receipt.json()['id']},
        ).scalar()
    assert Decimal(str(cost)) == Decimal('13.25')


def test_migration_iki_kez_calisinca_bozulmaz(client):
    import migrate_phase14_purchase

    migrate_phase14_purchase.main()
    migrate_phase14_purchase.main()
    assert client.get('/api/suppliers').status_code == 200


def test_tedarikci_verileri_tenant_bazli_izole(two_tenants):
    """Phase 12 entegrasyonu: bir firmanin tedarikcisi digerine gorunmez."""
    a, b = two_tenants
    suffix = unique_suffix()

    created = a.client.post('/api/suppliers', json={
        'code': f'IZOLE-{suffix}'[:50], 'name': f'A Tedarikci {suffix}'})
    assert created.status_code == 201, created.text
    supplier_id = created.json()['id']

    assert any(s['id'] == supplier_id for s in a.client.get('/api/suppliers').json())
    assert not any(s['id'] == supplier_id for s in b.client.get('/api/suppliers').json())
    assert b.client.get(f'/api/suppliers/{supplier_id}').status_code == 404


# ---------------- 8. Uctan uca ----------------

def test_uctan_uca_alim_satis_stok_tutarli(client, tracker, uoms):
    """Siparis -> mal kabul -> fatura -> satis zinciri stok tutarli mi."""
    supplier = make_supplier(client, tracker)
    product = make_product(client, tracker, stock='0')

    order = make_order(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '40', 'unit_price': '10.00'}])
    order_item = order['items'][0]
    assert stock_of(client, product['id']) == Decimal('0')

    receipt = make_receipt(client, tracker, supplier, [{
        'product_id': product['id'],
        'purchase_order_item_id': order_item['id'],
        'quantity': '40', 'accepted_quantity': '40', 'unit_price': '10.00',
    }], order=order)
    assert receipt.status_code == 201, receipt.text
    assert stock_of(client, product['id']) == Decimal('40')

    invoice = make_invoice(client, tracker, supplier, [
        {'product_id': product['id'], 'quantity': '40', 'unit_price': '10.00'}],
        purchase_receipt_id=receipt.json()['id'])
    assert invoice.status_code == 201, invoice.text
    assert stock_of(client, product['id']) == Decimal('40')

    customer = make_customer(client, tracker)
    sale = client.post('/api/sales', json={
        'customer_id': customer['id'],
        'items': [{'product_id': product['id'], 'quantity': 15,
                   'unit_price': '18.00'}],
    })
    assert sale.status_code == 201, sale.text
    tracker.add('sales', sale.json()['id'])
    assert stock_of(client, product['id']) == Decimal('25')
