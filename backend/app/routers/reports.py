"""Raporlama endpointleri (Phase 6) ve uyari endpointleri (Phase 9).

Ciro hesaplarinda iptal edilmis satislar (status='cancelled') HARIC tutulur:
iptal edilen bir satis gercek bir gelir degildir.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Customer, Invoice, Product, Sale, SalesItem

router = APIRouter(
    prefix='/api/reports',
    tags=['reports'],
    dependencies=[Depends(get_current_user)],
)

# Uyarilar ayni dosyada ama farkli bir URL onekinde durdugu icin ikinci bir router
# gerekiyor (Phase 9). main.py ikisini de include ediyor.
alerts_router = APIRouter(
    prefix='/api/alerts',
    tags=['alerts'],
    dependencies=[Depends(get_current_user)],
)

# Phase 3'teki Products sayfasi rozetiyle ayni esik
LOW_STOCK_THRESHOLD = 10
# Invoice modelinde due_date yok; vade olarak issued_date + 30 gun varsayiliyor
OVERDUE_DAYS = 30

# Ciroya sayilan satis durumlari
ACTIVE_STATUSES = ('pending', 'completed')

TURKISH_MONTHS = [
    'Oca', 'Sub', 'Mar', 'Nis', 'May', 'Haz',
    'Tem', 'Agu', 'Eyl', 'Eki', 'Kas', 'Ara',
]


def _month_label(d: date) -> str:
    return f'{TURKISH_MONTHS[d.month - 1]} {d.year}'


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _shift_months(d: date, months: int) -> date:
    """Ayin ilk gunune gore ay ekler/cikarir."""
    total = (d.year * 12 + (d.month - 1)) + months
    return date(total // 12, total % 12 + 1, 1)


@router.get('/sales-by-month')
def sales_by_month(
    months: int = Query(6, ge=1, le=24, description='Kac aylik gecmis'),
    db: Session = Depends(get_db),
):
    """Ay bazli toplam satis tutari ve adedi. Satis olmayan aylar 0 olarak doner."""
    today = date.today()
    start = _shift_months(_first_of_month(today), -(months - 1))

    month_col = func.date_trunc('month', Sale.sale_date).label('month')
    rows = (
        db.query(
            month_col,
            func.coalesce(func.sum(Sale.total_amount), 0).label('total'),
            func.count(Sale.id).label('count'),
        )
        .filter(Sale.sale_date >= start)
        .filter(Sale.status.in_(ACTIVE_STATUSES))
        .group_by(month_col)
        .order_by(month_col)
        .all()
    )

    # Veritabanindan gelenleri ay anahtarina gore sozluge al
    found = {}
    for row in rows:
        key = row.month.date() if hasattr(row.month, 'date') else row.month
        found[(key.year, key.month)] = (float(row.total or 0), int(row.count or 0))

    # Bos aylari 0 ile doldur - grafikte bosluk olusmasin
    result = []
    cursor = start
    for _ in range(months):
        total, count = found.get((cursor.year, cursor.month), (0.0, 0))
        result.append({
            'month': cursor.isoformat(),
            'label': _month_label(cursor),
            'total': round(total, 2),
            'count': count,
        })
        cursor = _shift_months(cursor, 1)
    return result


@router.get('/top-products')
def top_products(
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """En cok satilan urunler (miktar bazli). Iptal edilen satislar sayilmaz."""
    rows = (
        db.query(
            Product.id.label('product_id'),
            Product.name.label('name'),
            Product.sku.label('sku'),
            func.sum(SalesItem.quantity).label('quantity'),
            func.sum(SalesItem.total_price).label('revenue'),
        )
        .join(SalesItem, SalesItem.product_id == Product.id)
        .join(Sale, Sale.id == SalesItem.sale_id)
        .filter(Sale.status.in_(ACTIVE_STATUSES))
        .group_by(Product.id, Product.name, Product.sku)
        .order_by(func.sum(SalesItem.quantity).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            'product_id': r.product_id,
            'name': r.name,
            'sku': r.sku,
            'quantity': int(r.quantity or 0),
            'revenue': round(float(r.revenue or 0), 2),
        }
        for r in rows
    ]


@router.get('/revenue-summary')
def revenue_summary(db: Session = Depends(get_db)):
    """Bugun / bu hafta / bu ay / bu yil toplam ciro (iptaller haric)."""
    today = date.today()
    periods = {
        'today': today,
        'week': today - timedelta(days=today.weekday()),  # haftanin pazartesi gunu
        'month': today.replace(day=1),
        'year': today.replace(month=1, day=1),
    }

    summary = {}
    for key, start in periods.items():
        row = (
            db.query(
                func.coalesce(func.sum(Sale.total_amount), 0).label('total'),
                func.count(Sale.id).label('count'),
            )
            .filter(Sale.sale_date >= start)
            .filter(Sale.sale_date <= today)
            .filter(Sale.status.in_(ACTIVE_STATUSES))
            .one()
        )
        summary[key] = {
            'total': round(float(row.total or 0), 2),
            'count': int(row.count or 0),
            'since': start.isoformat(),
        }
    return summary


@router.get('/product/{product_id}/history')
def product_history(product_id: int, db: Session = Depends(get_db)):
    """Bir urunun satis gecmisi: tarih, musteri, miktar, tutar, satis durumu."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f'Product {product_id} bulunamadi')

    rows = (
        db.query(
            Sale.id.label('sale_id'),
            Sale.sale_date,
            Sale.status,
            Customer.name.label('customer_name'),
            SalesItem.quantity,
            SalesItem.unit_price,
            SalesItem.total_price,
        )
        .join(SalesItem, SalesItem.sale_id == Sale.id)
        .join(Customer, Customer.id == Sale.customer_id)
        .filter(SalesItem.product_id == product_id)
        .order_by(Sale.sale_date.desc(), Sale.id.desc())
        .all()
    )

    items = [
        {
            'sale_id': r.sale_id,
            'sale_date': r.sale_date.isoformat() if r.sale_date else None,
            'status': r.status,
            'customer_name': r.customer_name,
            'quantity': r.quantity,
            'unit_price': round(float(r.unit_price or 0), 2),
            'total_price': round(float(r.total_price or 0), 2),
        }
        for r in rows
    ]
    active = [i for i in items if i['status'] in ACTIVE_STATUSES]
    return {
        'product_id': product.id,
        'product_name': product.name,
        'sku': product.sku,
        'current_stock': product.stock,
        'total_sold': sum(i['quantity'] for i in active),
        'total_revenue': round(sum(i['total_price'] for i in active), 2),
        'history': items,
    }


# ---------------- Phase 9: Uyarilar ----------------

@alerts_router.get('/low-stock')
def low_stock(
    threshold: int = Query(LOW_STOCK_THRESHOLD, ge=0, le=1000),
    db: Session = Depends(get_db),
):
    """Stogu esigin altinda kalan urunler. En az stoklu once gelir."""
    rows = (
        db.query(Product)
        .filter(Product.stock < threshold)
        .order_by(Product.stock.asc(), Product.name.asc())
        .all()
    )
    return {
        'threshold': threshold,
        'count': len(rows),
        'out_of_stock': sum(1 for p in rows if (p.stock or 0) == 0),
        'items': [
            {'id': p.id, 'name': p.name, 'sku': p.sku, 'stock': p.stock or 0}
            for p in rows
        ],
    }


@alerts_router.get('/overdue-invoices')
def overdue_invoices(
    days: int = Query(OVERDUE_DAYS, ge=0, le=365),
    db: Session = Depends(get_db),
):
    """Kesilmis ama odenmemis ve vadesi gecmis faturalar.

    Invoice modelinde due_date alani olmadigi icin vade = issued_date + days
    olarak varsayiliyor.
    """
    today = date.today()
    cutoff = today - timedelta(days=days)

    rows = (
        db.query(Invoice, Customer.name.label('customer_name'))
        .outerjoin(Customer, Customer.id == Invoice.customer_id)
        .filter(Invoice.status == 'issued')
        .filter(Invoice.issued_date.isnot(None))
        .filter(Invoice.issued_date <= cutoff)
        .order_by(Invoice.issued_date.asc())
        .all()
    )

    items = []
    for invoice, customer_name in rows:
        items.append({
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'customer_id': invoice.customer_id,
            'customer_name': customer_name,
            'issued_date': invoice.issued_date.isoformat(),
            'due_date': (invoice.issued_date + timedelta(days=days)).isoformat(),
            'days_overdue': (today - invoice.issued_date).days - days,
            'total_amount': round(float(invoice.total_amount or 0), 2),
            'status': invoice.status,
        })

    return {
        'days': days,
        'count': len(items),
        'total_amount': round(sum(i['total_amount'] for i in items), 2),
        'items': items,
    }


@alerts_router.get('/summary')
def alerts_summary(db: Session = Depends(get_db)):
    """Navbar rozeti ve panel icin tek seferde ozet."""
    low = low_stock(threshold=LOW_STOCK_THRESHOLD, db=db)
    overdue = overdue_invoices(days=OVERDUE_DAYS, db=db)
    return {
        'total': low['count'] + overdue['count'],
        'low_stock': low,
        'overdue_invoices': overdue,
    }
