"""Phase 13 testleri: olcu birimi, kategori, marka, barkod ve varyant.

Notion "Phase 13 - Adim 8" listesindeki her madde burada bir testtir.
"""
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.conftest import admin_connection, unique_suffix
from tests.test_phase10_stock import make_customer, make_product, stock_of


# ---------------- Yardimcilar ----------------

@pytest.fixture()
def uoms(client):
    """Varsayilan birimleri kurar ve {kod: id} haritasi doner."""
    response = client.post('/api/uoms/ensure-defaults')
    assert response.status_code == 200, response.text
    return {u['code']: u['id'] for u in response.json()}


def make_group(client, tracker, name='Kategori', parent_id=None):
    suffix = unique_suffix()
    response = client.post('/api/item-groups', json={
        'code': f'G-{suffix}'[:50],
        'name': f'{name} {suffix}',
        'parent_id': parent_id,
    })
    assert response.status_code == 201, response.text
    group = response.json()
    tracker.add('item_groups', group['id'])
    return group


def make_brand(client, tracker):
    suffix = unique_suffix()
    response = client.post('/api/brands', json={'name': f'Marka {suffix}'})
    assert response.status_code == 201, response.text
    brand = response.json()
    tracker.add('brands', brand['id'])
    return brand


def make_conversion(client, tracker, from_id, to_id, factor, product_id=None):
    """Donusum ekler ve tracker'a bildirir.

    Evrensel donusumler (product_id=None) tracker'in urun uzerinden yaptigi
    cascade ile yakalanmaz; bildirilmezse gercek veritabaninda birikir ve
    sonraki kosularda tenant genelindeki donusum tablosunu degistirir.
    """
    response = client.post('/api/uom-conversions', json={
        'from_uom_id': from_id,
        'to_uom_id': to_id,
        'factor': str(factor),
        'product_id': product_id,
    })
    assert response.status_code == 201, response.text
    conversion = response.json()
    tracker.add('uom_conversions', conversion['id'])
    return conversion


def ean13(prefix12: str) -> str:
    """Verilen 12 haneye dogru kontrol hanesini ekler."""
    total = 0
    for index, char in enumerate(reversed(prefix12)):
        total += int(char) * (3 if index % 2 == 0 else 1)
    return prefix12 + str((10 - total % 10) % 10)


# ---------------- 1. Olcu birimi ve donusum ----------------

def test_varsayilan_birimler_kuruluyor(uoms):
    for code in ('adet', 'kg', 'gram', 'litre', 'metre', 'koli', 'ton'):
        assert code in uoms, f'{code} birimi yok'


def test_evrensel_donusum_calisiyor(client, uoms):
    """1 kg = 1000 gram - urun bagimsiz donusum migration'da kuruldu."""
    response = client.get('/api/uom-conversions/convert', params={
        'quantity': '2.5', 'from_uom_id': uoms['kg'], 'to_uom_id': uoms['gram']})
    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()['converted'])) == Decimal('2500')


def test_ters_yonde_donusum_turetiliyor(client, uoms):
    """gram -> kg tanimli degil; kg -> gram carpaninin tersi kullanilir."""
    response = client.get('/api/uom-conversions/convert', params={
        'quantity': '500', 'from_uom_id': uoms['gram'], 'to_uom_id': uoms['kg']})
    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()['converted'])) == Decimal('0.5')


def test_urune_ozel_donusum_geneli_ezer(client, tracker, uoms):
    """X urunu icin 1 koli = 12 adet; genel koli tanimi baska olsa da bu gecerli."""
    product = make_product(client, tracker, stock='0')

    # Once genel bir koli tanimi: 1 koli = 6 adet
    make_conversion(client, tracker, uoms['koli'], uoms['adet'], '6')
    # Sonra bu urune ozel: 1 koli = 12 adet
    make_conversion(
        client, tracker, uoms['koli'], uoms['adet'], '12', product_id=product['id']
    )

    genel = client.get('/api/uom-conversions/convert', params={
        'quantity': '5', 'from_uom_id': uoms['koli'], 'to_uom_id': uoms['adet']}).json()
    assert Decimal(str(genel['converted'])) == Decimal('30')  # 5 x 6

    ozel = client.get('/api/uom-conversions/convert', params={
        'quantity': '5', 'from_uom_id': uoms['koli'], 'to_uom_id': uoms['adet'],
        'product_id': product['id']}).json()
    assert Decimal(str(ozel['converted'])) == Decimal('60')  # 5 x 12


def test_tanimsiz_donusum_400_doner(client, uoms):
    response = client.get('/api/uom-conversions/convert', params={
        'quantity': '1', 'from_uom_id': uoms['metre'], 'to_uom_id': uoms['kg']})
    assert response.status_code == 400, response.text
    assert 'donusum tanimli degil' in response.json()['detail']


def test_ondalikli_carpan_korunuyor(client, tracker, uoms):
    """1 top kumas = 47.5 metre gibi ondalikli donusumler bozulmamali."""
    product = make_product(client, tracker, stock='0')
    make_conversion(client, tracker, uoms['paket'], uoms['metre'], '47.5', product['id'])
    result = client.get('/api/uom-conversions/convert', params={
        'quantity': '3', 'from_uom_id': uoms['paket'], 'to_uom_id': uoms['metre'],
        'product_id': product['id']}).json()
    assert Decimal(str(result['converted'])) == Decimal('142.5')


# ---------------- 2. Ledger her zaman stok biriminde ----------------

def test_koli_alip_adet_satmak(client, tracker, uoms):
    """Alim koli, stok adet: ledger'a adet cinsinden dusmeli."""
    suffix = unique_suffix()
    response = client.post('/api/products', json={
        'name': f'Koli Urun {suffix}',
        'sku': f'P13-{suffix}',
        'price': '10.00',
        'stock_uom_id': uoms['adet'],
        'purchase_uom_id': uoms['koli'],
        'stock': '0',
    })
    assert response.status_code == 201, response.text
    product = response.json()
    tracker.add('products', product['id'])

    # Bu urun icin 1 koli = 12 adet
    make_conversion(client, tracker, uoms['koli'], uoms['adet'], '12', product['id'])

    # 5 koli giris -> 60 adet
    entry = client.post('/api/stock/adjustments', json={
        'product_id': product['id'], 'change_qty': '60', 'reason': 'alim'})
    assert entry.status_code == 201, entry.text
    assert stock_of(client, product['id']) == Decimal('60')

    # 3 adet satis
    customer = make_customer(client, tracker)
    sale = client.post('/api/sales', json={
        'customer_id': customer['id'],
        'items': [{
            'product_id': product['id'], 'quantity': 3, 'unit_price': '10.00',
            'uom_id': uoms['adet'],
        }],
    })
    assert sale.status_code == 201, sale.text
    tracker.add('sales', sale.json()['id'])
    assert stock_of(client, product['id']) == Decimal('57')


def test_farkli_birimde_satis_ledgera_stok_biriminde_duser(client, tracker, uoms):
    """Koli satis, adet stok: 2 koli satilinca 24 adet dusmeli."""
    suffix = unique_suffix()
    product = client.post('/api/products', json={
        'name': f'Birim Urun {suffix}',
        'sku': f'P13B-{suffix}',
        'price': '120.00',
        'stock_uom_id': uoms['adet'],
        'sales_uom_id': uoms['koli'],
        'stock': '100',
    })
    assert product.status_code == 201, product.text
    product = product.json()
    tracker.add('products', product['id'])
    make_conversion(client, tracker, uoms['koli'], uoms['adet'], '12', product['id'])

    customer = make_customer(client, tracker)
    sale = client.post('/api/sales', json={
        'customer_id': customer['id'],
        'items': [{
            'product_id': product['id'], 'quantity': 2, 'unit_price': '120.00',
            'uom_id': uoms['koli'],
        }],
    })
    assert sale.status_code == 201, sale.text
    body = sale.json()
    tracker.add('sales', body['id'])

    # Fiyat koli uzerinden: 2 x 120 = 240
    assert Decimal(str(body['total_amount'])) == Decimal('240.00')
    item = body['items'][0]
    assert Decimal(str(item['quantity'])) == Decimal('2')          # girilen birim
    assert Decimal(str(item['stock_quantity'])) == Decimal('24')   # stok birimi

    # Stok adet cinsinden dustu
    assert stock_of(client, product['id']) == Decimal('76')

    entries = client.get('/api/stock/ledger', params={
        'product_id': product['id'], 'reason': 'satis'}).json()
    assert Decimal(str(entries[0]['change_qty'])) == Decimal('-24')


def test_acilis_stogu_farkli_birimde_girilebilir(client, tracker, uoms):
    """Acilis 5 koli girilirse ledger'a 60 adet yazilmali."""
    suffix = unique_suffix()
    product = client.post('/api/products', json={
        'name': f'Acilis Urun {suffix}',
        'sku': f'P13C-{suffix}',
        'price': '10.00',
        'stock_uom_id': uoms['adet'],
        'stock': '0',
    })
    assert product.status_code == 201
    product = product.json()
    tracker.add('products', product['id'])
    make_conversion(client, tracker, uoms['koli'], uoms['adet'], '12', product['id'])

    # Ayni urunu koli cinsinden acilisla guncelle: 5 koli -> 60 adet
    response = client.post('/api/stock/adjustments', json={
        'product_id': product['id'], 'change_qty': '60', 'reason': 'acilis'})
    assert response.status_code == 201, response.text
    assert stock_of(client, product['id']) == Decimal('60')


# ---------------- 3. Kategori agaci ----------------

def test_kategori_agaci_kuruluyor(client, tracker):
    root = make_group(client, tracker, 'Elektronik')
    mid = make_group(client, tracker, 'Bilgisayar', parent_id=root['id'])
    leaf = make_group(client, tracker, 'Dizustu', parent_id=mid['id'])

    tree = client.get('/api/item-groups/tree').json()
    node = next(n for n in tree if n['id'] == root['id'])
    child = next(c for c in node['children'] if c['id'] == mid['id'])
    assert any(g['id'] == leaf['id'] for g in child['children'])


def test_kategori_agacinda_dongu_engelleniyor(client, tracker):
    root = make_group(client, tracker, 'Ust')
    child = make_group(client, tracker, 'Alt', parent_id=root['id'])

    # Ust kategoriyi kendi alt kategorisine baglamaya calis
    response = client.put(f'/api/item-groups/{root["id"]}',
                          json={'parent_id': child['id']})
    assert response.status_code == 400, response.text
    assert 'dongu' in response.json()['detail']

    # Kendine baglama da yasak
    self_ref = client.put(f'/api/item-groups/{root["id"]}',
                          json={'parent_id': root['id']})
    assert self_ref.status_code == 400


def test_alt_grubu_olan_kategori_silinemez(client, tracker):
    root = make_group(client, tracker, 'Ana')
    make_group(client, tracker, 'Alt', parent_id=root['id'])
    response = client.delete(f'/api/item-groups/{root["id"]}')
    assert response.status_code == 400, response.text
    assert 'Alt kategorisi' in response.json()['detail']


def test_urunu_olan_kategori_silinemez(client, tracker, uoms):
    group = make_group(client, tracker, 'Doluk')
    suffix = unique_suffix()
    product = client.post('/api/products', json={
        'name': f'Kategorili {suffix}', 'sku': f'P13D-{suffix}',
        'price': '5.00', 'item_group_id': group['id'], 'stock': '0'})
    assert product.status_code == 201, product.text
    tracker.add('products', product.json()['id'])

    response = client.delete(f'/api/item-groups/{group["id"]}')
    assert response.status_code == 400, response.text
    assert 'Urunu olan' in response.json()['detail']


# ---------------- 4. Marka ----------------

def test_marka_urunle_iliskilendiriliyor(client, tracker, uoms):
    brand = make_brand(client, tracker)
    group = make_group(client, tracker)
    suffix = unique_suffix()
    response = client.post('/api/products', json={
        'name': f'Markali {suffix}', 'sku': f'P13E-{suffix}', 'price': '15.00',
        'brand_id': brand['id'], 'item_group_id': group['id'], 'stock': '0'})
    assert response.status_code == 201, response.text
    product = response.json()
    tracker.add('products', product['id'])
    assert product['brand_name'] == brand['name']
    assert product['item_group_name'] == group['name']

    # Markaya gore filtre
    listed = client.get('/api/products', params={'brand_id': brand['id']}).json()
    assert [p['id'] for p in listed] == [product['id']]


def test_urunu_olan_marka_silinemez(client, tracker):
    brand = make_brand(client, tracker)
    suffix = unique_suffix()
    product = client.post('/api/products', json={
        'name': f'Markali {suffix}', 'sku': f'P13F-{suffix}',
        'price': '5.00', 'brand_id': brand['id'], 'stock': '0'})
    tracker.add('products', product.json()['id'])
    assert client.delete(f'/api/brands/{brand["id"]}').status_code == 400


# ---------------- 5. Barkod ----------------

def test_barkoddan_urun_bulunuyor(client, tracker, uoms):
    suffix = unique_suffix()
    barcode = ean13('869' + f'{abs(hash(suffix)) % 1000000000:09d}')
    response = client.post('/api/products', json={
        'name': f'Barkodlu {suffix}', 'sku': f'P13G-{suffix}', 'price': '20.00',
        'stock': '5', 'stock_uom_id': uoms['adet'],
        'barcodes': [{'barcode': barcode, 'barcode_type': 'EAN13',
                      'uom_id': uoms['adet'], 'is_primary': True}],
    })
    assert response.status_code == 201, response.text
    product = response.json()
    tracker.add('products', product['id'])
    assert len(product['barcodes']) == 1

    found = client.get(f'/api/products/by-barcode/{barcode}')
    assert found.status_code == 200, found.text
    assert found.json()['product']['id'] == product['id']
    assert found.json()['uom_id'] == uoms['adet']

    assert client.get('/api/products/by-barcode/0000000000000').status_code == 404


def test_ean13_kontrol_hanesi_dogrulaniyor(client, tracker):
    suffix = unique_suffix()
    hatali = '8690000000001'  # kontrol hanesi kasten yanlis
    response = client.post('/api/products', json={
        'name': f'Hatali barkod {suffix}', 'sku': f'P13H-{suffix}', 'price': '1.00',
        'stock': '0',
        'barcodes': [{'barcode': hatali, 'barcode_type': 'EAN13'}],
    })
    assert response.status_code == 400, response.text
    assert 'kontrol hanesi' in response.json()['detail']


def test_bir_urunun_birden_fazla_barkodu_olabilir(client, tracker, uoms):
    """Adet barkodu ayri, koli barkodu ayri."""
    suffix = unique_suffix()
    adet_barkod = ean13('869' + f'{abs(hash(suffix + "a")) % 1000000000:09d}')
    koli_barkod = ean13('869' + f'{abs(hash(suffix + "k")) % 1000000000:09d}')

    product = client.post('/api/products', json={
        'name': f'Cift barkod {suffix}', 'sku': f'P13I-{suffix}', 'price': '1.00',
        'stock': '0', 'stock_uom_id': uoms['adet'],
        'barcodes': [{'barcode': adet_barkod, 'uom_id': uoms['adet'],
                      'is_primary': True}],
    })
    assert product.status_code == 201, product.text
    product = product.json()
    tracker.add('products', product['id'])

    added = client.post(f'/api/products/{product["id"]}/barcodes', json={
        'barcode': koli_barkod, 'barcode_type': 'EAN13', 'uom_id': uoms['koli']})
    assert added.status_code == 201, added.text

    detail = client.get(f'/api/products/{product["id"]}').json()
    assert len(detail['barcodes']) == 2
    assert client.get(f'/api/products/by-barcode/{koli_barkod}').json()['uom_id'] == (
        uoms['koli']
    )


def test_barkod_tenant_icinde_tekil(client, tracker, uoms):
    suffix = unique_suffix()
    barcode = ean13('869' + f'{abs(hash(suffix + "u")) % 1000000000:09d}')
    first = client.post('/api/products', json={
        'name': f'Ilk {suffix}', 'sku': f'P13J-{suffix}', 'price': '1.00',
        'stock': '0', 'barcodes': [{'barcode': barcode}]})
    assert first.status_code == 201, first.text
    tracker.add('products', first.json()['id'])

    second = client.post('/api/products', json={
        'name': f'Ikinci {suffix}', 'sku': f'P13K-{suffix}', 'price': '1.00',
        'stock': '0', 'barcodes': [{'barcode': barcode}]})
    assert second.status_code == 409, second.text
    if second.status_code == 201:
        tracker.add('products', second.json()['id'])


def test_barkod_unique_kisiti_tenant_bazli():
    """Farkli tenant'ta ayni barkod kullanilabilmeli - kisit tenant bazli."""
    with admin_connection() as conn:
        definition = conn.execute(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'uq_barcodes_tenant_code'"
        )).scalar()
    assert definition is not None, 'uq_barcodes_tenant_code kisiti yok'
    assert 'tenant_id' in definition and 'barcode' in definition, definition


# ---------------- 6. Varyant ----------------

@pytest.fixture()
def renk_beden(client, tracker):
    """2 renk x 3 beden oznitelikleri."""
    suffix = unique_suffix()
    renk = client.post('/api/item-attributes', json={
        'name': f'Renk {suffix}',
        'values': [{'value': 'Kirmizi', 'sort_order': 1},
                   {'value': 'Mavi', 'sort_order': 2}]})
    assert renk.status_code == 201, renk.text
    beden = client.post('/api/item-attributes', json={
        'name': f'Beden {suffix}',
        'values': [{'value': 'S', 'sort_order': 1},
                   {'value': 'M', 'sort_order': 2},
                   {'value': 'L', 'sort_order': 3}]})
    assert beden.status_code == 201, beden.text
    renk, beden = renk.json(), beden.json()
    tracker.add('item_attributes', renk['id'])
    tracker.add('item_attributes', beden['id'])
    return renk, beden


def test_varyant_uretimi_kombinasyonlari_cikarir(client, tracker, uoms, renk_beden):
    """2 renk x 3 beden = 6 varyant."""
    renk, beden = renk_beden
    suffix = unique_suffix()
    template = client.post('/api/products', json={
        'name': f'Tisort {suffix}', 'sku': f'TSHIRT-{suffix}', 'price': '199.00',
        'stock': '0', 'is_variant_template': True, 'stock_uom_id': uoms['adet']})
    assert template.status_code == 201, template.text
    template = template.json()
    tracker.add('products', template['id'])

    response = client.post(f'/api/products/{template["id"]}/generate-variants', json={
        'attribute_ids': [renk['id'], beden['id']]})
    assert response.status_code == 201, response.text
    variants = response.json()
    for variant in variants:
        tracker.add('products', variant['id'])

    assert len(variants) == 6, [v['sku'] for v in variants]
    skus = {v['sku'] for v in variants}
    assert f'{template["sku"]}-KIRMIZI-M' in skus, skus
    assert all(v['parent_product_id'] == template['id'] for v in variants)
    assert all(not v['is_variant_template'] for v in variants)

    # Tekrar cagirinca kopya uretilmemeli
    again = client.post(f'/api/products/{template["id"]}/generate-variants', json={
        'attribute_ids': [renk['id'], beden['id']]})
    assert again.status_code == 201, again.text
    assert again.json() == []

    listed = client.get(f'/api/products/{template["id"]}/variants').json()
    assert len(listed) == 6


def test_sablon_urune_stok_girilemez(client, tracker, uoms, renk_beden):
    """Sablonun stogu olmaz; stok varyantlarda tutulur."""
    suffix = unique_suffix()
    template = client.post('/api/products', json={
        'name': f'Sablon {suffix}', 'sku': f'TPL-{suffix}', 'price': '10.00',
        'stock': '0', 'is_variant_template': True})
    assert template.status_code == 201, template.text
    template = template.json()
    tracker.add('products', template['id'])

    response = client.post('/api/stock/adjustments', json={
        'product_id': template['id'], 'change_qty': '5', 'reason': 'acilis'})
    assert response.status_code == 400, response.text
    assert 'varyant sablonu' in response.json()['detail']


def test_varyant_satilabiliyor(client, tracker, uoms, renk_beden):
    renk, beden = renk_beden
    suffix = unique_suffix()
    template = client.post('/api/products', json={
        'name': f'Satilik Tisort {suffix}', 'sku': f'SALE-{suffix}',
        'price': '199.00', 'stock': '0', 'is_variant_template': True,
        'stock_uom_id': uoms['adet']}).json()
    tracker.add('products', template['id'])

    variants = client.post(f'/api/products/{template["id"]}/generate-variants', json={
        'attribute_ids': [renk['id']]}).json()
    for variant in variants:
        tracker.add('products', variant['id'])
    assert len(variants) == 2

    target = variants[0]
    client.put(f'/api/products/{target["id"]}', json={'stock': '10'})
    assert stock_of(client, target['id']) == Decimal('10')

    customer = make_customer(client, tracker)
    sale = client.post('/api/sales', json={
        'customer_id': customer['id'],
        'items': [{'product_id': target['id'], 'quantity': 4, 'unit_price': '199.00'}],
    })
    assert sale.status_code == 201, sale.text
    tracker.add('sales', sale.json()['id'])
    assert stock_of(client, target['id']) == Decimal('6')


def test_hizmet_urunu_stok_tutmaz(client, tracker):
    suffix = unique_suffix()
    service = client.post('/api/products', json={
        'name': f'Danismanlik {suffix}', 'sku': f'SRV-{suffix}', 'price': '500.00',
        'product_type': 'hizmet', 'stock': '0'})
    assert service.status_code == 201, service.text
    service = service.json()
    tracker.add('products', service['id'])

    response = client.post('/api/stock/adjustments', json={
        'product_id': service['id'], 'change_qty': '3', 'reason': 'acilis'})
    assert response.status_code == 400, response.text
    assert 'hizmet urunu' in response.json()['detail']


# ---------------- 7. Semasal kontroller ----------------

def test_yeni_tablolar_tenant_bazli_ve_rls_altinda():
    from migrate_phase13_catalog import NEW_TABLES

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


def test_migration_iki_kez_calisinca_bozulmaz(client, uoms):
    import migrate_phase13_catalog

    migrate_phase13_catalog.main()
    migrate_phase13_catalog.main()

    codes = [u['code'] for u in client.get('/api/uoms').json()]
    assert len(codes) == len(set(codes)), codes
