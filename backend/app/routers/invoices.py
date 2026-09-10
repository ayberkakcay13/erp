"""Invoice endpointleri.

Phase 15 oncesi: fatura her zaman bir Sale'den uretilirdi (`sale_id`
zorunlu, kalemsizdi - PDF kalemleri Sale'den okurdu).

Phase 15: fatura artik MALI BELGE - stok hareketi yaratmaz (stok sevkiyatta
gitmistir). `POST /api/sales/{sale_id}/invoice` (uyum katmani) korunur;
yeni `POST /api/invoices` kalemli fatura ve `delivery_note_id` baglantisi
sunar. `due_date` bossa `document_service` musterinin vade gun sayisindan
hesaplar (bkz. `document_service._sales_invoice_effects`).
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import PAYMENT_STATUSES, DeliveryNote, DocStatus, Invoice, InvoiceItem, Sale, SalesItem, User
from ..pdf import build_invoice_pdf
from ..schemas import (
    CancelRequest,
    InvoiceCreate,
    InvoiceCreateV2,
    InvoiceResponse,
    InvoiceStatusUpdate,
    InvoiceUpdate,
)
from ..services import document_service, sales_order_service
from ..services.tenant_service import require_module

router = APIRouter(
    tags=['invoices'],
    dependencies=[Depends(get_current_user), Depends(require_module('invoice'))],
)


def _serialize(invoice: Invoice) -> dict:
    """Fatura + belge yasam dongusu alanlari."""
    return {
        'id': invoice.id,
        'sale_id': invoice.sale_id,
        'delivery_note_id': invoice.delivery_note_id,
        'invoice_number': invoice.invoice_number,
        'customer_id': invoice.customer_id,
        'issued_date': invoice.issued_date,
        'due_date': invoice.due_date,
        'subtotal': invoice.subtotal,
        'tax_total': invoice.tax_total,
        'total_amount': invoice.total_amount,
        'status': invoice.status,
        'payment_status': invoice.payment_status,
        'docstatus': invoice.docstatus,
        'docstatus_label': DocStatus.LABELS.get(invoice.docstatus),
        'submitted_at': invoice.submitted_at,
        'submitted_by': invoice.submitted_by,
        'cancelled_at': invoice.cancelled_at,
        'cancelled_by': invoice.cancelled_by,
        'cancel_reason': invoice.cancel_reason,
        'created_at': invoice.created_at,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
                'uom_id': item.uom_id,
                'uom_code': item.uom.code if item.uom else None,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'tax_rate': item.tax_rate,
                'total_price': item.total_price,
            }
            for item in invoice.items
        ],
    }


def _get_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.items).joinedload(InvoiceItem.product),
            joinedload(Invoice.items).joinedload(InvoiceItem.uom),
        )
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail=f'Invoice {invoice_id} bulunamadi')
    return invoice


@router.post(
    '/api/sales/{sale_id}/invoice',
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_invoice_from_sale(
    sale_id: int,
    payload: InvoiceCreate | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Uyum katmani: eski `/api/sales/{id}/invoice` akisi (Phase 10-14).

    Fatura kalemleri sale.items'tan birebir kopyalanir. Yeni kod
    `POST /api/invoices` kullanmali.
    """
    sale = db.get(Sale, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail=f'Sale {sale_id} bulunamadi')

    existing = db.query(Invoice).filter(Invoice.sale_id == sale_id).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f'Sale {sale_id} icin zaten fatura var: {existing.invoice_number}',
        )

    payload = payload or InvoiceCreate()
    # Para hesabi Decimal ile yapilir (Phase 10 kurali: float yok)
    tax_rate = Decimal(str(payload.tax_rate))
    subtotal = Decimal(str(sale.total_amount))
    total = (subtotal * (Decimal('1') + tax_rate)).quantize(Decimal('0.01'))

    # Phase 11: fatura numarasi ONAY aninda atanir (FT-2026-00001).
    # Taslak faturalar numara tuketmez - silinen taslak numara boslugu birakmaz.
    invoice = Invoice(
        sale_id=sale.id,
        invoice_number=None,
        customer_id=sale.customer_id,
        issued_date=payload.issued_date or date.today(),
        subtotal=subtotal,
        tax_total=(total - subtotal).quantize(Decimal('0.01')),
        total_amount=total,
        status='draft',
        payment_status='odenmedi',
    )
    for item in sale.items:
        invoice.items.append(
            InvoiceItem(
                product_id=item.product_id,
                uom_id=item.uom_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                tax_rate=(tax_rate * 100),
                total_price=item.total_price,
            )
        )
    db.add(invoice)
    db.flush()
    if not payload.save_as_draft:
        document_service.submit(db, invoice, user_id=current_user.id)
        invoice.status = 'issued'
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f'Sale {sale_id} icin zaten fatura var'
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura olusturulamadi: {exc}')
    return _serialize(_get_or_404(db, invoice.id))


@router.post('/api/invoices', response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreateV2,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kalemli fatura olusturur - satistan bagimsiz veya bir sevkiyata bagli."""
    delivery_note = None
    if payload.delivery_note_id is not None:
        delivery_note = db.get(DeliveryNote, payload.delivery_note_id)
        if delivery_note is None:
            raise HTTPException(
                status_code=404,
                detail=f'Sevkiyat {payload.delivery_note_id} bulunamadi',
            )

    invoice = Invoice(
        sale_id=delivery_note.sales_order_id if delivery_note else None,
        delivery_note_id=payload.delivery_note_id,
        invoice_number=None,
        customer_id=payload.customer_id,
        issued_date=payload.issued_date or date.today(),
        due_date=payload.due_date,
        status='draft',
        payment_status='odenmedi',
        note=payload.note,
    )
    for entry in payload.items:
        net = (Decimal(str(entry.quantity)) * Decimal(str(entry.unit_price))).quantize(
            Decimal('0.01')
        )
        invoice.items.append(
            InvoiceItem(
                product_id=entry.product_id,
                uom_id=entry.uom_id,
                quantity=entry.quantity,
                unit_price=entry.unit_price,
                tax_rate=entry.tax_rate,
                total_price=net,
            )
        )
    subtotal = sum((sales_order_service.to_decimal(i.total_price) for i in invoice.items),
                   sales_order_service.ZERO)
    tax_total = sum(
        (sales_order_service.money(
            sales_order_service.to_decimal(i.total_price)
            * sales_order_service.to_decimal(i.tax_rate) / Decimal('100')
        ) for i in invoice.items),
        sales_order_service.ZERO,
    )
    invoice.subtotal = sales_order_service.money(subtotal)
    invoice.tax_total = sales_order_service.money(tax_total)
    invoice.total_amount = sales_order_service.money(subtotal + tax_total)

    db.add(invoice)
    db.flush()
    if not payload.save_as_draft:
        document_service.submit(db, invoice, user_id=current_user.id)
        invoice.status = 'issued'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura olusturulamadi: {exc}')
    return _serialize(_get_or_404(db, invoice.id))


@router.get('/api/invoices', response_model=list[InvoiceResponse])
def list_invoices(db: Session = Depends(get_db)):
    invoices = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.items).joinedload(InvoiceItem.product),
            joinedload(Invoice.items).joinedload(InvoiceItem.uom),
        )
        .order_by(Invoice.id)
        .all()
    )
    return [_serialize(i) for i in invoices]


@router.get('/api/invoices/{invoice_id}', response_model=InvoiceResponse)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return _serialize(_get_or_404(db, invoice_id))


@router.put('/api/invoices/{invoice_id}', response_model=InvoiceResponse)
def update_invoice_status(
    invoice_id: int, payload: InvoiceStatusUpdate, db: Session = Depends(get_db)
):
    """Odeme durumunu gunceller (draft / issued / paid).

    `status` odeme is akisidir, `docstatus` belge yasam dongusu - ikisi ayri.
    Iptal edilmis fatura uzerinde durum degistirilemez.
    """
    invoice = _get_or_404(db, invoice_id)
    if invoice.docstatus == DocStatus.CANCELLED:
        raise HTTPException(
            status_code=400, detail='Iptal edilmis fatura uzerinde islem yapilamaz'
        )
    invoice.status = payload.status
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Durum guncellenemedi: {exc}')
    return _serialize(_get_or_404(db, invoice_id))


@router.put('/api/invoices/{invoice_id}/payment', response_model=InvoiceResponse)
def update_payment_status(
    invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)
):
    """Odeme durumunu (odenmedi/kismi/odendi) ve/veya vadeyi gunceller."""
    invoice = _get_or_404(db, invoice_id)
    if payload.payment_status is not None:
        if payload.payment_status not in PAYMENT_STATUSES:
            raise HTTPException(
                status_code=400, detail=f'Gecersiz odeme durumu: {payload.payment_status}'
            )
        invoice.payment_status = payload.payment_status
    if payload.due_date is not None:
        invoice.due_date = payload.due_date
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Odeme durumu guncellenemedi: {exc}')
    return _serialize(_get_or_404(db, invoice_id))


@router.post('/api/invoices/{invoice_id}/submit', response_model=InvoiceResponse)
def submit_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Taslak faturayi keser: numara bu anda atanir ve belge kilitlenir."""
    invoice = _get_or_404(db, invoice_id)
    document_service.submit(db, invoice, user_id=current_user.id)
    invoice.status = 'issued'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura kesilemedi: {exc}')
    return _serialize(_get_or_404(db, invoice_id))


@router.post('/api/invoices/{invoice_id}/cancel', response_model=InvoiceResponse)
def cancel_invoice(
    invoice_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kesilmis faturayi iptal eder. Numara iade edilmez - seride bosluk olmaz."""
    invoice = _get_or_404(db, invoice_id)
    document_service.cancel(
        db, invoice, user_id=current_user.id,
        reason=payload.reason if payload else None,
    )
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura iptal edilemedi: {exc}')
    return _serialize(_get_or_404(db, invoice_id))


@router.delete('/api/invoices/{invoice_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Yalnizca TASLAK fatura silinebilir."""
    invoice = _get_or_404(db, invoice_id)
    document_service.ensure_deletable(invoice)
    try:
        db.delete(invoice)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Fatura silinemedi: {exc}')
    return None


@router.get('/api/invoices/{invoice_id}/pdf')
def download_invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):
    """Faturayi PDF olarak dondurur.

    Sale'e bagli eski faturalarda kalemler `sale.items`'tan, yeni kalemli
    faturalarda `invoice.items`'tan okunur.
    """
    invoice = _get_or_404(db, invoice_id)

    customer = None
    sale_for_pdf = None

    if invoice.items:
        items = [
            {
                'name': item.product.name if item.product else f'Urun #{item.product_id}',
                'sku': item.product.sku if item.product else None,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'total_price': item.total_price,
            }
            for item in invoice.items
        ]
        from ..models import Customer  # gec import: dongu onlemek icin

        customer = db.get(Customer, invoice.customer_id)
        # pdf.py `sale.total_amount`'i ARA TOPLAM olarak okur; kalemli
        # faturada (baglantili Sale yoksa) hafif bir yer tutucu yeterli -
        # invoice nesnesinin kendisini mutasyona ugratmamak icin ayri nesne.
        sale_for_pdf = SimpleNamespace(total_amount=invoice.subtotal or invoice.total_amount)
    else:
        sale = (
            db.query(Sale)
            .options(joinedload(Sale.items).joinedload(SalesItem.product),
                     joinedload(Sale.customer))
            .filter(Sale.id == invoice.sale_id)
            .first()
        )
        if sale is None:
            raise HTTPException(
                status_code=404,
                detail=f'Faturaya bagli satis (#{invoice.sale_id}) bulunamadi',
            )
        items = [
            {
                'name': item.product.name if item.product else f'Urun #{item.product_id}',
                'sku': item.product.sku if item.product else None,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'total_price': item.total_price,
            }
            for item in sale.items
        ]
        customer = sale.customer
        sale_for_pdf = sale

    try:
        content = build_invoice_pdf(invoice, sale_for_pdf, customer, items)
    except Exception as exc:  # PDF uretimi basarisizsa anlamli hata don
        raise HTTPException(status_code=500, detail=f'PDF olusturulamadi: {exc}')

    filename = f'{invoice.invoice_number or f"fatura-{invoice.id}"}.pdf'
    return Response(
        content=content,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(len(content)),
        },
    )
