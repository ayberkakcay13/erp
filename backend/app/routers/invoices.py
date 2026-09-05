"""Invoice endpointleri. Fatura her zaman bir satistan uretilir."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..pdf import build_invoice_pdf
from ..models import Invoice, Sale, SalesItem
from ..schemas import InvoiceCreate, InvoiceResponse, InvoiceStatusUpdate

router = APIRouter(
    tags=['invoices'],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    '/api/sales/{sale_id}/invoice',
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_invoice_from_sale(
    sale_id: int, payload: InvoiceCreate | None = None, db: Session = Depends(get_db)
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
    total = round(sale.total_amount * (1 + payload.tax_rate), 2)

    invoice = Invoice(
        sale_id=sale.id,
        invoice_number=f'INV-{sale.id}-{int(datetime.utcnow().timestamp())}',
        customer_id=sale.customer_id,
        issued_date=payload.issued_date or date.today(),
        total_amount=total,
        status='draft',
    )
    db.add(invoice)
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
    return invoice


@router.get('/api/invoices', response_model=list[InvoiceResponse])
def list_invoices(db: Session = Depends(get_db)):
    return db.query(Invoice).order_by(Invoice.id).all()


@router.get('/api/invoices/{invoice_id}', response_model=InvoiceResponse)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f'Invoice {invoice_id} bulunamadi')
    return invoice


@router.put('/api/invoices/{invoice_id}', response_model=InvoiceResponse)
def update_invoice_status(
    invoice_id: int, payload: InvoiceStatusUpdate, db: Session = Depends(get_db)
):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f'Invoice {invoice_id} bulunamadi')
    invoice.status = payload.status
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Durum guncellenemedi: {exc}')
    db.refresh(invoice)
    return invoice


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
