"""Raporlama endpointleri (Phase 6) ve uyari endpointleri (Phase 9).

Ciro hesaplarinda iptal edilmis satislar (status='cancelled') HARIC tutulur:
iptal edilen bir satis gercek bir gelir degildir.
"""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Customer,
    Invoice,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    Sale,
    SalesItem,
    Supplier,
)
from ..services import stock_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/reports',
    tags=['reports'],
    dependencies=[Depends(get_current_user), Depends(require_module('reports'))],
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


def _money(value) -> Decimal:
    """Tutari kurusa yuvarlar (float kullanmadan)."""
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


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
        found[(key.year, key.month)] = (Decimal(str(row.total or 0)), int(row.count or 0))

    # Bos aylari 0 ile doldur - grafikte bosluk olusmasin
    result = []
    cursor = start
    for _ in range(months):
        total, count = found.get((cursor.year, cursor.month), (Decimal('0'), 0))
        result.append({
            'month': cursor.isoformat(),
            'label': _month_label(cursor),
            'total': _money(total),
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
            # Phase 13: miktar toplami STOK BIRIMI uzerinden; kalem farkli
            # birimde girilmis olabilir (koli satis, adet stok).
            func.sum(
                func.coalesce(SalesItem.stock_quantity, SalesItem.quantity)
            ).label('quantity'),
            func.sum(SalesItem.total_price).label('revenue'),
        )
        .join(SalesItem, SalesItem.product_id == Product.id)
        .join(Sale, Sale.id == SalesItem.sale_id)
        .filter(Sale.status.in_(ACTIVE_STATUSES))
        .group_by(Product.id, Product.name, Product.sku)
        .order_by(
            func.sum(
                func.coalesce(SalesItem.stock_quantity, SalesItem.quantity)
            ).desc()
        )
        .limit(limit)
        .all()
    )
    return [
        {
            'product_id': r.product_id,
            'name': r.name,
            'sku': r.sku,
            'quantity': Decimal(str(r.quantity or 0)),
            'revenue': _money(r.revenue),
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
            'total': _money(row.total),
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
            'unit_price': _money(r.unit_price),
            'total_price': _money(r.total_price),
        }
        for r in rows
    ]
    active = [i for i in items if i['status'] in ACTIVE_STATUSES]
    return {
        'product_id': product.id,
        'product_name': product.name,
        'sku': product.sku,
        'current_stock': stock_service.get_stock(db, product.id),
        'total_sold': sum((Decimal(str(i['quantity'])) for i in active), Decimal('0')),
        'total_revenue': _money(sum((i['total_price'] for i in active), Decimal('0'))),
        'history': items,
    }


# ---------------- Phase 9: Uyarilar ----------------

@router.get('/purchase-summary')
def purchase_summary(
    months: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """Aylik alim toplami (onayli mal kabuller uzerinden)."""
    start = _first_of_month(_shift_months(date.today(), months - 1))
    rows = (
        db.query(
            PurchaseReceipt.receipt_date,
            PurchaseReceiptItem.accepted_quantity,
            PurchaseReceiptItem.unit_price,
        )
        .join(
            PurchaseReceiptItem,
            PurchaseReceiptItem.purchase_receipt_id == PurchaseReceipt.id,
        )
        .filter(
            PurchaseReceipt.docstatus == 1,
            PurchaseReceipt.receipt_date >= start,
        )
        .all()
    )

    buckets = {}
    for receipt_date, quantity, unit_price in rows:
        key = _first_of_month(receipt_date)
        buckets[key] = buckets.get(key, Decimal('0')) + _money(
            Decimal(str(quantity)) * Decimal(str(unit_price))
        )

    result = []
    cursor = start
    today_month = _first_of_month(date.today())
    while cursor <= today_month:
        result.append({
            'month': cursor.isoformat(),
            'label': _month_label(cursor),
            'total': _money(buckets.get(cursor, Decimal('0'))),
        })
        cursor = _shift_months(cursor, 1)
    return result


@router.get('/supplier-performance')
def supplier_performance(db: Session = Depends(get_db)):
    """Tedarikci bazli toplam alim, teslim gecikmesi ve red orani."""
    rows = (
        db.query(
            PurchaseReceipt.supplier_id,
            Supplier.name,
            PurchaseReceipt.receipt_date,
            PurchaseOrder.expected_date,
            PurchaseReceiptItem.accepted_quantity,
            PurchaseReceiptItem.rejected_quantity,
            PurchaseReceiptItem.unit_price,
        )
        .join(Supplier, Supplier.id == PurchaseReceipt.supplier_id)
        .join(
            PurchaseReceiptItem,
            PurchaseReceiptItem.purchase_receipt_id == PurchaseReceipt.id,
        )
        .outerjoin(PurchaseOrder, PurchaseOrder.id == PurchaseReceipt.purchase_order_id)
        .filter(PurchaseReceipt.docstatus == 1)
        .all()
    )

    stats = {}
    for supplier_id, name, receipt_date, expected_date, accepted, rejected, price in rows:
        entry = stats.setdefault(supplier_id, {
            'supplier_id': supplier_id,
            'supplier_name': name,
            'total_amount': Decimal('0'),
            'accepted_quantity': Decimal('0'),
            'rejected_quantity': Decimal('0'),
            'delay_days': [],
        })
        accepted = Decimal(str(accepted))
        rejected = Decimal(str(rejected))
        entry['total_amount'] += _money(accepted * Decimal(str(price)))
        entry['accepted_quantity'] += accepted
        entry['rejected_quantity'] += rejected
        if expected_date is not None and receipt_date is not None:
            entry['delay_days'].append((receipt_date - expected_date).days)

    result = []
    for entry in stats.values():
        handled = entry['accepted_quantity'] + entry['rejected_quantity']
        delays = entry.pop('delay_days')
        entry['total_amount'] = _money(entry['total_amount'])
        entry['reject_rate'] = (
            _money(entry['rejected_quantity'] * Decimal('100') / handled)
            if handled > 0 else Decimal('0.00')
        )
        entry['average_delay_days'] = (
            round(sum(delays) / len(delays), 1) if delays else None
        )
        result.append(entry)
    result.sort(key=lambda r: r['total_amount'], reverse=True)
    return result


@router.get('/pending-purchase-orders')
def pending_purchase_orders(db: Session = Depends(get_db)):
    """Teslim alinmayi bekleyen onayli siparisler."""
    orders = (
        db.query(PurchaseOrder)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(
            PurchaseOrder.docstatus == 1,
            PurchaseOrder.status.in_(('beklemede', 'kismi_teslim')),
        )
        .order_by(PurchaseOrder.expected_date.is_(None), PurchaseOrder.expected_date)
        .all()
    )

    today = date.today()
    result = []
    for order in orders:
        result.append({
            'id': order.id,
            'po_number': order.po_number,
            'supplier_id': order.supplier_id,
            'supplier_name': order.supplier.name if order.supplier else None,
            'order_date': order.order_date,
            'expected_date': order.expected_date,
            'status': order.status,
            'grand_total': order.grand_total,
            'is_overdue': (
                order.expected_date is not None and order.expected_date < today
            ),
        })
    return result


@router.get('/product-purchase-history')
def product_purchase_history(
    product_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Urunun alim fiyat gecmisi - kar hesabinin temeli."""
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail=f'Product {product_id} bulunamadi')

    rows = (
        db.query(
            PurchaseReceipt.id,
            PurchaseReceipt.receipt_number,
            PurchaseReceipt.receipt_date,
            Supplier.name,
            PurchaseReceiptItem.accepted_quantity,
            PurchaseReceiptItem.stock_quantity,
            PurchaseReceiptItem.unit_price,
        )
        .join(
            PurchaseReceiptItem,
            PurchaseReceiptItem.purchase_receipt_id == PurchaseReceipt.id,
        )
        .join(Supplier, Supplier.id == PurchaseReceipt.supplier_id)
        .filter(
            PurchaseReceiptItem.product_id == product_id,
            PurchaseReceipt.docstatus == 1,
        )
        .order_by(PurchaseReceipt.receipt_date.desc(), PurchaseReceipt.id.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            'receipt_id': receipt_id,
            'receipt_number': receipt_number,
            'receipt_date': receipt_date,
            'supplier_name': supplier_name,
            'quantity': quantity,
            'stock_quantity': stock_quantity,
            'unit_price': unit_price,
        }
        for (
            receipt_id, receipt_number, receipt_date, supplier_name,
            quantity, stock_quantity, unit_price,
        ) in rows
    ]


@alerts_router.get('/low-stock')
def low_stock(
    threshold: int = Query(LOW_STOCK_THRESHOLD, ge=0, le=1000),
    warehouse_id: int | None = Query(None, description='Sadece bu deponun stogu'),
    db: Session = Depends(get_db),
):
    """Stogu esigin altinda kalan urunler. En az stoklu once gelir.

    Phase 10: stok `products` kolonundan degil, stok defterinden hesaplanir.
    Hic hareketi olmayan urun 0 stok sayilir, bu yuzden tum urunler taranir.
    """
    limit_qty = stock_service.to_decimal(threshold)
    products = db.query(Product).all()
    balances = stock_service.get_stock_map(
        db, [p.id for p in products], warehouse_id=warehouse_id
    )

    items = []
    for product in products:
        quantity = balances.get(product.id, stock_service.ZERO)
        if quantity < limit_qty:
            items.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'stock': quantity,
            })
    items.sort(key=lambda i: (i['stock'], i['name']))

    return {
        'threshold': threshold,
        'warehouse_id': warehouse_id,
        'count': len(items),
        'out_of_stock': sum(1 for i in items if i['stock'] <= stock_service.ZERO),
        'items': items,
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
            'total_amount': _money(invoice.total_amount),
            'status': invoice.status,
        })

    return {
        'days': days,
        'count': len(items),
        'total_amount': _money(sum((i['total_amount'] for i in items), Decimal('0'))),
        'items': items,
    }


@alerts_router.get('/overdue-purchase-orders')
def overdue_purchase_orders(db: Session = Depends(get_db)):
    """Teslim tarihi gecmis onayli siparisler."""
    today = date.today()
    orders = (
        db.query(PurchaseOrder)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(
            PurchaseOrder.docstatus == 1,
            PurchaseOrder.status.in_(('beklemede', 'kismi_teslim')),
            PurchaseOrder.expected_date.isnot(None),
            PurchaseOrder.expected_date < today,
        )
        .order_by(PurchaseOrder.expected_date)
        .all()
    )
    return [
        {
            'id': order.id,
            'po_number': order.po_number,
            'supplier_name': order.supplier.name if order.supplier else None,
            'expected_date': order.expected_date,
            'days_late': (today - order.expected_date).days,
            'grand_total': order.grand_total,
        }
        for order in orders
    ]


@alerts_router.get('/summary')
def alerts_summary(db: Session = Depends(get_db)):
    """Navbar rozeti ve panel icin tek seferde ozet."""
    low = low_stock(threshold=LOW_STOCK_THRESHOLD, db=db)
    overdue = overdue_invoices(days=OVERDUE_DAYS, db=db)
    late_orders = overdue_purchase_orders(db=db)
    return {
        'total': low['count'] + overdue['count'] + len(late_orders),
        'low_stock': low,
        'overdue_invoices': overdue,
        'overdue_purchase_orders': {'count': len(late_orders), 'items': late_orders},
    }
