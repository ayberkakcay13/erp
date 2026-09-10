"""Phase 11 testleri: belge durumu, numaralandirma ve denetim izi.

Notion "Phase 11 - Adim 6" listesindeki her madde burada bir testtir.
"""
import re
import threading
from decimal import Decimal

from sqlalchemy import text

from app.database import SessionLocal, engine
from app.models import DocStatus
from app.services import naming_service, tenant_context
from tests.conftest import unique_suffix
from tests.test_phase10_stock import (
    make_customer,
    make_product,
    make_sale,
    make_warehouse,
    stock_of,
)


def make_draft_sale(client, tracker, customer_id, items):
    response = client.post('/api/sales', json={
        'customer_id': customer_id,
        'save_as_draft': True,
        'items': items,
    })
    assert response.status_code == 201, response.text
    tracker.add('sales', response.json()['id'])
    return response.json()


def make_invoice(client, tracker, sale_id, draft=False, tax_rate='0'):
    response = client.post(f'/api/sales/{sale_id}/invoice', json={
        'tax_rate': tax_rate,
        'save_as_draft': draft,
    })
    assert response.status_code == 201, response.text
    tracker.add('invoices', response.json()['id'])
    return response.json()


# ---------------- 1. docstatus altyapisi ----------------

def test_satis_varsayilan_olarak_onayli_olusur(client, tracker):
    """Varsayilan davranis "olustur ve onayla" - Phase 1-10 akisi korunur."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')

    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'},
    ]).json()

    assert sale['docstatus'] == DocStatus.SUBMITTED
    assert sale['docstatus_label'] == 'onayli'
    assert sale['submitted_at'] is not None
    assert stock_of(client, product['id']) == Decimal('8')


def test_taslak_satis_stok_hareketi_yazmaz(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')

    sale = make_draft_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 3, 'unit_price': '10.00'},
    ])
    assert sale['docstatus'] == DocStatus.DRAFT
    assert sale['docstatus_label'] == 'taslak'
    assert stock_of(client, product['id']) == Decimal('10')

    # Onaylaninca stok hareket eder
    response = client.post(f'/api/sales/{sale["id"]}/submit')
    assert response.status_code == 200, response.text
    assert response.json()['docstatus'] == DocStatus.SUBMITTED
    assert stock_of(client, product['id']) == Decimal('7')


def test_status_ve_docstatus_bagimsiz(client, tracker):
    """`status` is akisi, `docstatus` belge yasam dongusu - ikisi ayri kavram."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 1, 'unit_price': '10.00'},
    ]).json()

    response = client.put(f'/api/sales/{sale["id"]}', json={'status': 'completed'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'completed'
    assert body['docstatus'] == DocStatus.SUBMITTED  # belge hala onayli
    assert stock_of(client, product['id']) == Decimal('9')  # stok etkilenmedi


# ---------------- 2. Degismezlik kurallari ----------------

def test_taslak_kayit_duzenlenebilir(client, tracker, default_tenant_id):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_draft_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'},
    ])

    with tenant_context.tenant_scope(default_tenant_id):
        session = SessionLocal()
        try:
            from app.models import Sale

            record = session.get(Sale, sale['id'])
            record.total_amount = Decimal('99.00')
            session.commit()  # taslak: serbestce degisir
            session.refresh(record)
            assert record.total_amount == Decimal('99.0000')
        finally:
            session.close()


def test_onayli_kayit_update_denemesi_reddedilir(client, tracker, default_tenant_id):
    """Onayli belgede is alani degistirilemez - kural event listener'da."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'},
    ]).json()

    with tenant_context.tenant_scope(default_tenant_id):
        session = SessionLocal()
        try:
            from app.models import DocumentImmutableError, Sale

            record = session.get(Sale, sale['id'])
            record.total_amount = Decimal('1.00')
            try:
                session.commit()
                raise AssertionError('Onayli belge degistirilebildi')
            except DocumentImmutableError as exc:
                assert 'degistirilemez' in str(exc)
        finally:
            session.rollback()
            session.close()


def test_onayli_kayit_delete_denemesi_400(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'},
    ]).json()

    response = client.delete(f'/api/sales/{sale["id"]}')
    assert response.status_code == 400, response.text
    assert 'silinemez' in response.json()['detail']


def test_taslak_kayit_silinebilir(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_draft_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'},
    ])

    assert client.delete(f'/api/sales/{sale["id"]}').status_code == 204
    assert client.get(f'/api/sales/{sale["id"]}').status_code == 404


def test_iptal_edilen_belge_tekrar_onaylanamaz(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'},
    ]).json()

    cancelled = client.post(f'/api/sales/{sale["id"]}/cancel',
                            json={'reason': 'Musteri vazgecti'})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()['docstatus'] == DocStatus.CANCELLED
    assert cancelled.json()['cancel_reason'] == 'Musteri vazgecti'

    response = client.post(f'/api/sales/{sale["id"]}/submit')
    assert response.status_code == 400, response.text
    assert 'tekrar onaylanamaz' in response.json()['detail']


def test_taslak_belge_iptal_edilemez(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_draft_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'},
    ])
    response = client.post(f'/api/sales/{sale["id"]}/cancel')
    assert response.status_code == 400, response.text


# ---------------- 3. Onay/iptal - stok entegrasyonu (Phase 10) ----------------

def test_onayda_stok_dusuyor_iptalde_geri_geliyor(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='20')
    sale = make_draft_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 6, 'unit_price': '10.00'},
    ])

    assert stock_of(client, product['id']) == Decimal('20')
    client.post(f'/api/sales/{sale["id"]}/submit')
    assert stock_of(client, product['id']) == Decimal('14')
    client.post(f'/api/sales/{sale["id"]}/cancel', json={'reason': 'test'})
    assert stock_of(client, product['id']) == Decimal('20')

    # Ledger'da iki hareket: satis ve satis_iptal (silme yok, ters kayit var)
    entries = client.get('/api/stock/ledger',
                         params={'product_id': product['id']}).json()
    reasons = [e['reason'] for e in entries]
    assert reasons.count('satis') == 1
    assert reasons.count('satis_iptal') == 1


def test_transfer_iptalinde_stok_geri_doner(client, tracker):
    source = make_warehouse(client, tracker)
    target = make_warehouse(client, tracker)
    product = make_product(client, tracker, stock='30', warehouse_id=source['id'])

    transfer = client.post('/api/transfers', json={
        'from_warehouse_id': source['id'],
        'to_warehouse_id': target['id'],
        'items': [{'product_id': product['id'], 'quantity': 10}],
    })
    assert transfer.status_code == 201, transfer.text
    transfer = transfer.json()
    tracker.add('stock_transfers', transfer['id'])
    assert transfer['docstatus'] == DocStatus.SUBMITTED
    assert stock_of(client, product['id'], target['id']) == Decimal('10')

    response = client.post(f'/api/transfers/{transfer["id"]}/cancel',
                           json={'reason': 'Yanlis depo'})
    assert response.status_code == 200, response.text
    assert stock_of(client, product['id'], source['id']) == Decimal('30')
    assert stock_of(client, product['id'], target['id']) == Decimal('0')


# ---------------- 4. Numaralandirma ----------------

def test_fatura_numarasi_seri_formatinda(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 1, 'unit_price': '100.00'},
    ]).json()

    invoice = make_invoice(client, tracker, sale['id'], tax_rate='0.20')
    assert re.fullmatch(r'FT-\d{4}-\d{5}', invoice['invoice_number']), (
        invoice['invoice_number']
    )
    assert invoice['docstatus'] == DocStatus.SUBMITTED
    assert Decimal(str(invoice['total_amount'])) == Decimal('120.00')


def test_taslak_fatura_numara_tuketmez(client, tracker, default_tenant_id):
    """Numara ONAY aninda atanir; silinen taslak seride bosluk birakmaz."""
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 1, 'unit_price': '10.00'},
    ]).json()

    invoice = make_invoice(client, tracker, sale['id'], draft=True)
    assert invoice['docstatus'] == DocStatus.DRAFT
    assert invoice['invoice_number'] is None

    before = _series_counter('invoice', default_tenant_id)
    assert client.delete(f'/api/invoices/{invoice["id"]}').status_code == 204
    assert _series_counter('invoice', default_tenant_id) == before  # tuketilmedi


def test_numaralar_ardisik_ve_atlamasiz(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')

    numbers = []
    for _ in range(3):
        sale = make_sale(client, tracker, customer['id'], [
            {'product_id': product['id'], 'quantity': 1, 'unit_price': '10.00'},
        ]).json()
        numbers.append(make_invoice(client, tracker, sale['id'])['invoice_number'])

    sequence = [int(n.rsplit('-', 1)[1]) for n in numbers]
    assert sequence == list(range(sequence[0], sequence[0] + 3)), sequence


def test_es_zamanli_numara_isteklerinde_tekrar_yok(client, tracker, default_tenant_id):
    """100 es zamanli istek: hicbir numara tekrar etmemeli, atlama olmamali."""
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(20)

    def take_numbers():
        # Seriler tenant bazli; her thread kendi baglamini kurar
        with tenant_context.tenant_scope(default_tenant_id):
            session = SessionLocal()
            try:
                barrier.wait(timeout=60)
                batch = [
                    naming_service.get_next_number(
                        session, 'delivery_note', tenant_id=default_tenant_id
                    )
                    for _ in range(5)
                ]
                session.commit()
                with lock:
                    results.extend(batch)
            except Exception:  # noqa: BLE001
                session.rollback()
                raise
            finally:
                session.close()

    threads = [threading.Thread(target=take_numbers) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert len(results) == 100, f'{len(results)} numara uretildi'
    assert len(set(results)) == 100, 'tekrar eden numara var'

    sequence = sorted(int(n.rsplit('-', 1)[1]) for n in results)
    assert sequence == list(range(sequence[0], sequence[0] + 100)), 'seride atlama var'


def test_yil_degisiminde_sayac_sifirlanir(client, tracker, default_tenant_id):
    """Gelecek yil icin seri acildiginda sayac sifirdan baslar."""
    from tests.conftest import admin_connection

    with tenant_context.tenant_scope(default_tenant_id):
        session = SessionLocal()
        try:
            future = 2099
            number = naming_service.get_next_number(
                session, 'delivery_note', year=future, tenant_id=default_tenant_id
            )
            session.commit()
            assert number == f'IR-{future}-00001', number
        finally:
            session.close()
    with admin_connection() as conn:
        conn.execute(text('DELETE FROM naming_series WHERE year = :y'), {'y': 2099})


def _series_counter(doc_type: str, tenant_id: int) -> int:
    from datetime import date

    from tests.conftest import admin_connection

    with admin_connection() as conn:
        return conn.execute(
            text(
                'SELECT current_number FROM naming_series '
                'WHERE doc_type = :d AND year = :y AND tenant_id = :t'
            ),
            {'d': doc_type, 'y': date.today().year, 't': tenant_id},
        ).scalar() or 0


def test_naming_series_endpointi(client, tracker):
    response = client.get('/api/naming-series')
    assert response.status_code == 200, response.text
    series = {s['doc_type']: s for s in response.json()}
    assert 'invoice' in series
    assert series['invoice']['prefix'] == 'FT'
    assert series['invoice']['next_number'].startswith('FT-')


def test_sayac_geriye_alinamaz(client, tracker):
    series = next(s for s in client.get('/api/naming-series').json()
                  if s['doc_type'] == 'invoice')
    if series['current_number'] == 0:
        return  # geriye alinacak bir sey yok
    response = client.put(f'/api/naming-series/{series["id"]}',
                          json={'current_number': series['current_number'] - 1})
    assert response.status_code == 400, response.text
    assert 'geriye alinamaz' in response.json()['detail']


# ---------------- 5. Denetim izi ----------------

def test_alan_degisikligi_audit_loga_duser(client, tracker):
    customer = make_customer(client, tracker)

    response = client.put(f'/api/customers/{customer["id"]}',
                          json={'phone': '05559998877'})
    assert response.status_code == 200, response.text

    logs = client.get(f'/api/audit-log/customers/{customer["id"]}').json()
    updates = [log for log in logs if log['action'] == 'update']
    assert any(
        log['field_name'] == 'phone'
        and log['new_value'] == '05559998877'
        and log['old_value'] == '05550000000'
        for log in updates
    ), updates
    # Kaydi olusturma da loglanmis olmali
    assert any(log['action'] == 'create' for log in logs)


def test_degismeyen_alan_loglanmaz(client, tracker):
    customer = make_customer(client, tracker)
    before = len(client.get(f'/api/audit-log/customers/{customer["id"]}').json())

    # Ayni degeri tekrar gonder - satir eklenmemeli
    client.put(f'/api/customers/{customer["id"]}', json={'name': customer['name']})
    after = len(client.get(f'/api/audit-log/customers/{customer["id"]}').json())
    assert after == before, 'degismeyen alan icin log satiri atildi'


def test_sifre_alani_audit_loga_dusmez(client, tracker):
    """Hassas alanlar hicbir kosulda loglanmaz."""
    logs = client.get('/api/audit-log', params={'table': 'users', 'limit': 1000}).json()
    sensitive = [
        log for log in logs
        if log['field_name'] in ('hashed_password', 'password')
    ]
    assert sensitive == [], sensitive


def test_onay_ve_iptal_audit_loga_duser(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='10')
    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 1, 'unit_price': '10.00'},
    ]).json()
    client.post(f'/api/sales/{sale["id"]}/cancel', json={'reason': 'test'})

    # Phase 15: audit_logs.table_name artik 'sales_orders' (tablo yeniden
    # adlandirildi).
    logs = client.get(f'/api/audit-log/sales_orders/{sale["id"]}').json()
    actions = {log['action'] for log in logs}
    assert 'submit' in actions, actions
    assert 'cancel' in actions, actions


def test_audit_log_kullaniciyi_kaydeder(client, tracker):
    customer = make_customer(client, tracker)
    logs = client.get(f'/api/audit-log/customers/{customer["id"]}').json()
    assert logs, 'log satiri yok'
    assert any(log['user_email'] for log in logs), 'kullanici bilgisi eksik'


def test_audit_log_sadece_admin(client, tracker, admin_token):
    """Sales rolundeki kullanici denetim izini goremez."""
    suffix = unique_suffix()
    email = f'p11-sales-{suffix}@erptest.com'
    created = client.post('/api/auth/register', json={
        'email': email, 'password': 'sales-123456',
        'full_name': 'Phase 11 Sales', 'role': 'sales',
    })
    assert created.status_code == 201, created.text
    user_id = created.json()['id']
    try:
        token = client.post('/api/auth/login', json={
            'email': email, 'password': 'sales-123456'}).json()['access_token']
        response = client.get(
            '/api/audit-log', headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 403, response.text
    finally:
        from tests.conftest import admin_connection

        with admin_connection() as conn:
            conn.execute(
                text('DELETE FROM audit_logs WHERE user_id = :i'), {'i': user_id}
            )
            conn.execute(text('DELETE FROM users WHERE id = :i'), {'i': user_id})


# ---------------- 6. Semasal kontroller ----------------

def test_belge_tablolarinda_docstatus_kolonu_var():
    with engine.connect() as conn:
        for table in ('sales_orders', 'invoices', 'stock_transfers',
                      'quotations', 'delivery_notes'):
            found = conn.execute(
                text(
                    'SELECT 1 FROM information_schema.columns '
                    'WHERE table_name = :t AND column_name = :c'
                ),
                {'t': table, 'c': 'docstatus'},
            ).first()
            assert found is not None, f'{table}.docstatus yok'


def test_audit_indexleri_var():
    """Log tablosu hizla buyur; index olmadan sorgular cokerdi."""
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'audit_logs'")
            )
        }
    assert 'ix_audit_table_record' in names, names
    assert 'ix_audit_created_at' in names, names


def test_migration_iki_kez_calisinca_bozulmaz(client, tracker):
    customer = make_customer(client, tracker)
    product = make_product(client, tracker, stock='5')
    sale = make_sale(client, tracker, customer['id'], [
        {'product_id': product['id'], 'quantity': 1, 'unit_price': '10.00'},
    ]).json()

    import migrate_phase11_documents

    migrate_phase11_documents.main()
    migrate_phase11_documents.main()

    # Onayli satis onayli kalir, seriler cift kayit olmaz
    assert client.get(f'/api/sales/{sale["id"]}').json()['docstatus'] == (
        DocStatus.SUBMITTED
    )
    doc_types = [s['doc_type'] for s in client.get('/api/naming-series').json()]
    assert len(doc_types) == len(set(doc_types)), doc_types
