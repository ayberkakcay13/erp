"""Adim 8: uctan uca senaryo testi (urllib ile, ekstra bagimlilik yok)."""
import json
import time
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8000'
failures = []

# Phase 5'ten sonra tum is endpointleri giris istiyor; asagida bir test
# kullanicisiyla giris yapilip token buraya konuyor.
TOKEN = None


def call(method, path, body=None, token='default'):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    active = TOKEN if token == 'default' else token
    if active:
        headers['Authorization'] = f'Bearer {active}'
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (json.loads(raw) if raw else None)


def check(label, cond, detail=''):
    print(('  OK   ' if cond else '  FAIL ') + label + (f'  [{detail}]' if detail else ''))
    if not cond:
        failures.append(label)


suffix = str(int(time.time()))

print('0. Giris (Phase 5: tum is endpointleri token istiyor)')
code, _ = call('GET', '/api/customers', token=None)
check('token\'siz erisim -> 401', code == 401, f'HTTP {code}')

# Sistemde kullanici yoksa ilk kayit otomatik admin olur; varsa bu hesapla giris yapilir.
TEST_ADMIN = 'fullflow-test@erptest.com'
TEST_PASS = 'fullflow123'
code, _ = call('POST', '/api/auth/register', {
    'email': TEST_ADMIN, 'password': TEST_PASS, 'full_name': 'Full Flow Test'}, token=None)
if code not in (201, 401, 409):
    print(f'  (register yaniti: HTTP {code})')

code, tok = call('POST', '/api/auth/login',
                 {'email': TEST_ADMIN, 'password': TEST_PASS}, token=None)
if code != 200:
    raise SystemExit(
        f'\nGiris yapilamadi (HTTP {code}). Bu test icin bir kez su kullaniciyi olustur:\n'
        f'  e-posta: {TEST_ADMIN}  sifre: {TEST_PASS}\n'
        f'  (admin olarak giris yapip Kullanicilar sayfasindan ekleyebilirsin)'
    )
TOKEN = tok['access_token']
check('giris basarili', bool(TOKEN))
check('token ile erisim aciliyor', call('GET', '/api/customers')[0] == 200)

print('\n1. Customer olustur')
code, cust = call('POST', '/api/customers', {
    'name': 'Zeynep Kaya', 'email': f'zeynep{suffix}@ornek.com', 'phone': '05441112233'})
check('POST /api/customers -> 201', code == 201, f'HTTP {code}')
cid = cust['id']
print(f'   customer_id = {cid}')

print('\n2. 3 Product olustur')
pids = []
specs = [('Mouse', 450.0, 100), ('Kulaklik', 1250.0, 40), ('Webcam', 890.0, 25)]
for name, price, stock in specs:
    code, p = call('POST', '/api/products', {
        'name': name, 'sku': f'SKU-{name.upper()[:3]}-{suffix}',
        'price': price, 'stock': stock})
    check(f'POST /api/products ({name}) -> 201', code == 201, f'HTTP {code}')
    pids.append(p['id'])
print(f'   product_ids = {pids}')

print('\n3. Sale olustur (2 urun)')
code, sale = call('POST', '/api/sales', {
    'customer_id': cid, 'sale_date': '2026-09-05',
    'items': [
        {'product_id': pids[0], 'quantity': 4, 'unit_price': 450.0},
        {'product_id': pids[1], 'quantity': 2, 'unit_price': 1250.0},
    ]})
check('POST /api/sales -> 201', code == 201, f'HTTP {code}')
expected = 4 * 450.0 + 2 * 1250.0
check(f'total_amount == {expected}', abs(sale['total_amount'] - expected) < 0.01,
      f"gelen: {sale['total_amount']}")
sid = sale['id']
print(f'   sale_id = {sid}')

print('\n3b. Stok otomatik dustu mu?')
code, p0 = call('GET', f'/api/products/{pids[0]}')
check('Mouse stok 100 -> 96', p0['stock'] == 96, f"gelen: {p0['stock']}")
code, p1 = call('GET', f'/api/products/{pids[1]}')
check('Kulaklik stok 40 -> 38', p1['stock'] == 38, f"gelen: {p1['stock']}")
code, p2 = call('GET', f'/api/products/{pids[2]}')
check('Webcam stok degismedi (25)', p2['stock'] == 25, f"gelen: {p2['stock']}")

print('\n3c. Yetersiz stokta satis reddediliyor mu?')
code, err = call('POST', '/api/sales', {'customer_id': cid, 'items': [
    {'product_id': pids[2], 'quantity': 9999, 'unit_price': 890.0}]})
check('stoktan fazla miktar -> 400', code == 400, f'HTTP {code}')
check('hata mesaji stok yetersiz diyor',
      'stok yetersiz' in str(err.get('detail', '')), str(err.get('detail'))[:60])
code, p2b = call('GET', f'/api/products/{pids[2]}')
check('reddedilen satista stok degismedi', p2b['stock'] == 25, f"gelen: {p2b['stock']}")

print('\n4. Sale bilgisini GET ile cek (detayli response)')
code, got = call('GET', f'/api/sales/{sid}')
check('GET /api/sales/{id} -> 200', code == 200, f'HTTP {code}')
check('customer bilgisi var', got.get('customer') is not None)
check('customer adi dogru', got['customer']['name'] == 'Zeynep Kaya')
check('2 item dondu', len(got['items']) == 2, f"{len(got['items'])} item")
check('item urun isimleri dolu', all(i['product_name'] for i in got['items']),
      ', '.join(str(i['product_name']) for i in got['items']))
check('item SKU\'lari dolu', all(i['product_sku'] for i in got['items']))
check('satir toplamlari dogru',
      all(abs(i['total_price'] - i['quantity'] * i['unit_price']) < 0.01 for i in got['items']))

print('\n5. Invoice olustur (KDV %20)')
code, inv = call('POST', f'/api/sales/{sid}/invoice', {'tax_rate': 0.20})
check('POST /api/sales/{id}/invoice -> 201', code == 201, f'HTTP {code}')
check('total_amount KDV dahil', abs(inv['total_amount'] - round(expected * 1.2, 2)) < 0.01,
      f"{inv['total_amount']} (beklenen {round(expected * 1.2, 2)})")
check('invoice_number uretildi', str(inv['invoice_number']).startswith(f'INV-{sid}-'),
      inv['invoice_number'])
check('baslangic status draft', inv['status'] == 'draft', inv['status'])
iid = inv['id']

print('\n6. Invoice GET')
code, got_inv = call('GET', f'/api/invoices/{iid}')
check('GET /api/invoices/{id} -> 200', code == 200, f'HTTP {code}')
check('sale_id eslesiyor', got_inv['sale_id'] == sid)
check('customer_id eslesiyor', got_inv['customer_id'] == cid)

print('\n7. Invoice status -> paid')
code, paid = call('PUT', f'/api/invoices/{iid}', {'status': 'paid'})
check('PUT /api/invoices/{id} -> 200', code == 200, f'HTTP {code}')
check('status = paid', paid['status'] == 'paid', paid['status'])
code, recheck = call('GET', f'/api/invoices/{iid}')
check('kalici (GET ile dogrulandi)', recheck['status'] == 'paid', recheck['status'])

print('\n8. Satis iptali stogu geri ekliyor mu?')
# Bu satista Mouse'tan 4, Kulaklik'tan 2 adet vardi (stoklar 96 ve 38'e dusmustu)
code, cancelled = call('PUT', f'/api/sales/{sid}', {'status': 'cancelled'})
check('PUT status=cancelled -> 200', code == 200, f'HTTP {code}')
check('status cancelled', cancelled['status'] == 'cancelled', cancelled['status'])
code, p0c = call('GET', f'/api/products/{pids[0]}')
check('Mouse stok 96 -> 100 (geri eklendi)', p0c['stock'] == 100, f"gelen: {p0c['stock']}")
code, p1c = call('GET', f'/api/products/{pids[1]}')
check('Kulaklik stok 38 -> 40 (geri eklendi)', p1c['stock'] == 40, f"gelen: {p1c['stock']}")

print('\n8b. Tekrar cancelled denendiginde stok ikinci kez eklenmemeli (idempotent)')
call('PUT', f'/api/sales/{sid}', {'status': 'cancelled'})
call('PUT', f'/api/sales/{sid}', {'status': 'cancelled'})
code, p0d = call('GET', f'/api/products/{pids[0]}')
check('Mouse stok hala 100', p0d['stock'] == 100, f"gelen: {p0d['stock']}")
code, p1d = call('GET', f'/api/products/{pids[1]}')
check('Kulaklik stok hala 40', p1d['stock'] == 40, f"gelen: {p1d['stock']}")

print('\n8c. Iptal geri alinirsa stok yeniden dusuluyor mu?')
code, back = call('PUT', f'/api/sales/{sid}', {'status': 'completed'})
check('PUT status=completed -> 200', code == 200, f'HTTP {code}')
code, p0e = call('GET', f'/api/products/{pids[0]}')
check('Mouse stok 100 -> 96 (yeniden dusuldu)', p0e['stock'] == 96, f"gelen: {p0e['stock']}")
code, p1e = call('GET', f'/api/products/{pids[1]}')
check('Kulaklik stok 40 -> 38 (yeniden dusuldu)', p1e['stock'] == 38, f"gelen: {p1e['stock']}")

print('\n8d. pending <-> completed gecisi stogu etkilemiyor')
call('PUT', f'/api/sales/{sid}', {'status': 'pending'})
code, p0f = call('GET', f'/api/products/{pids[0]}')
check('Mouse stok hala 96', p0f['stock'] == 96, f"gelen: {p0f['stock']}")
call('PUT', f'/api/sales/{sid}', {'status': 'completed'})
code, p0g = call('GET', f'/api/products/{pids[0]}')
check('Mouse stok hala 96', p0g['stock'] == 96, f"gelen: {p0g['stock']}")

print('\nBONUS: hatali istekler')
code, _ = call('POST', f'/api/sales/{sid}/invoice', {})
check('ayni sale icin 2. fatura -> 409', code == 409, f'HTTP {code}')
code, _ = call('GET', '/api/sales/999999')
check('olmayan sale -> 404', code == 404, f'HTTP {code}')
code, _ = call('POST', '/api/sales', {'customer_id': 999999, 'items': [
    {'product_id': pids[0], 'quantity': 1, 'unit_price': 1}]})
check('olmayan customer ile sale -> 404', code == 404, f'HTTP {code}')

print('\n' + '=' * 55)
if failures:
    print(f'SONUC: {len(failures)} KONTROL BASARISIZ')
    for f in failures:
        print('  -', f)
    raise SystemExit(1)
print('SONUC: TUM KONTROLLER BASARILI - uctan uca akis calisiyor')
