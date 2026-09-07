"""Invoice endpointleri. Fatura her zaman bir satistan uretilir."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..pdf import build_invoice_pdf
from ..models import DocStatus, Invoice, Sale, SalesItem, User
from ..schemas import (
    CancelRequest, InvoiceCreate, InvoiceResponse, InvoiceStatusUpdate,
)
from ..services import document_service
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
        'invoice_number': invoice.invoice_number,
        'customer_id': invoice.customer_id,
        'issued_date': invoice.issued_date,
        'total_amount': invoice.total_amount,
        'status': invoice.status,
        'docstatus': invoice.docstatus,
        'docstatus_label': DocStatus.LABELS.get(invoice.docstatus),
        'submitted_at': invoice.submitted_at,
        'submitted_by': invoice.submitted_by,
        'cancelled_at': invoice.cancelled_at,
        'cancelled_by': invoice.cancelled_by,
        'cancel_reason': invoice.cancel_reason,
        'created_at': invoice.created_at,
    }


def _get_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
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
    total = (
        Decimal(str(sale.total_amount)) * (Decimal('1') + Decimal(str(payload.tax_rate)))
    ).quantize(Decimal('0.01'))

    # Phase 11: fatura numarasi ONAY aninda atanir (FT-2026-00001).
    # Taslak faturalar numara tuketmez - silinen taslak numara boslugu birakmaz.
    invoice = Invoice(
        sale_id=sale.id,
        invoice_number=None,
        customer_id=sale.customer_id,
        issued_date=payload.issued_date or date.today(),
        total_amount=total,
        status='draft',
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
    db.refresh(invoice)
    return _serialize(invoice)


@router.get('/api/invoices', response_model=list[InvoiceResponse])
def list_invoices(db: Session = Depends(get_db)):
    return [_serialize(i) for i in db.query(Invoice).order_by(Invoice.id).all()]


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
    db.refresh(invoice)
    return _serialize(invoice)


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
    db.refresh(invoice)
    return _serialize(invoice)


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
    db.refresh(invoice)
    return _serialize(invoice)


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

    Fatura kaydinda urun kalemleri yok (sadece sale_id var), o yuzden
    kalemler ilgili satistan cekiliyor.
    """
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f'Invoice {invoice_id} bulunamadi')

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

    try:
        content = build_invoice_pdf(invoice, sale, sale.customer, items)
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
