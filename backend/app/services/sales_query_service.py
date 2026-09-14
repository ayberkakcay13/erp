"""Phase 19: Dashboard + musteri/urun detay pencereleri icin GERCEK veri sorgulari.

Phase 18'de bu endpoint'lerin govdesi app/mocks/ altindaki statik veriyi
donduruyordu; burada ayni sozlesme (response sekli) korunarak SQLAlchemy
uzerinden gercek sales_orders/sales_order_items sorgulanir.

Kasitli olarak supabase-py / RPC KULLANILMAZ: repo'nun tamami mevcut
`get_db()` SQLAlchemy session'i uzerinden calisir, tenant izolasyonu da
(Phase 12) bu session'a bagli SET LOCAL ROLE + RLS ile saglanir. Ayri bir
Supabase REST client'i bu izolasyonun disinda kalir.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from math import ceil
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..models import SalesOrder, SalesOrderItem

# Ciroya sayilan durumlar (reports.py ile ayni kural) - yalniz 'cancelled' haric
ACTIVE_STATUSES = ('pending', 'completed', 'confirmed', 'partially_delivered', 'delivered')

# Gercek SalesOrder.status degerlerini UI'nin bekledigi
# pending/processing/delivered uc-durumuna esler (Phase 16-17 mock tasarimi).
_STATUS_MAP = {
    'draft': 'pending',
    'pending': 'pending',
    'confirmed': 'pending',
    'partially_delivered': 'processing',
    'delivered': 'delivered',
    'completed': 'delivered',
}

TURKISH_MONTHS = ['Oca', 'Sub', 'Mar', 'Nis', 'May', 'Haz',
                   'Tem', 'Agu', 'Eyl', 'Eki', 'Kas', 'Ara']


def _ui_status(raw: str) -> str:
    return _STATUS_MAP.get(raw, raw)


def parse_date(value: Optional[str]) -> date:
    """ISO tarih string'ini date'e cevirir; gecersiz/bos ise bugunu doner."""
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return date.today()


def _money(value) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal('0.01')))


def _order_label(order: SalesOrder) -> str:
    return order.so_number or f'#SO-{order.id}'


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _serialize_order(order: SalesOrder) -> dict:
    """Bir SalesOrder'i, musteri modal'inin bekledigi satir seklinde dondurur.

    'product' ilk kalemin urunu + varsa fazlasi icin '(+N urun)' eki -
    Devam Eden/Son Siparisler tablosu tek bir urun kolonu gosterir.
    """
    items = order.items
    if items:
        first_name = items[0].product.name if items[0].product else '-'
        product_label = f'{first_name} (+{len(items) - 1} urun)' if len(items) > 1 else first_name
    else:
        product_label = '-'
    return {
        'id': _order_label(order),
        'customer': order.customer.name if order.customer else '-',
        'product': product_label,
        'order_date': _iso(order.sale_date),
        'delivery_date': _iso(order.promised_delivery_date),
        'amount': _money(order.total_amount),
        'status': _ui_status(order.status),
    }


def _serialize_item(item: SalesOrderItem) -> dict:
    """Bir SalesOrderItem'i, urun modal'inin bekledigi satir seklinde dondurur.

    'amount' siparisin toplami degil, bu kalemin satır toplamidir.
    """
    order = item.sales_order
    return {
        'id': f'{_order_label(order)}-{item.id}',
        'customer': order.customer.name if order.customer else '-',
        'product': item.product.name if item.product else '-',
        'order_date': _iso(order.sale_date),
        'delivery_date': _iso(order.promised_delivery_date),
        'amount': _money(item.total_price),
        'status': _ui_status(order.status),
    }


# ---------------- Musteri/urun siparis listeleri ----------------

def get_customer_orders(db: Session, customer_id: int, status: Optional[str] = None) -> list[dict]:
    """Musteriye ait siparisler (iptaller haric - siparis takibi icin anlamsiz)."""
    orders = (
        db.query(SalesOrder)
        .options(joinedload(SalesOrder.items).joinedload(SalesOrderItem.product))
        .filter(SalesOrder.customer_id == customer_id, SalesOrder.status != 'cancelled')
        .order_by(SalesOrder.sale_date.desc(), SalesOrder.id.desc())
        .all()
    )
    rows = [_serialize_order(o) for o in orders]
    return [r for r in rows if r['status'] == status] if status else rows


def get_product_orders(db: Session, product_id: int, status: Optional[str] = None) -> list[dict]:
    """Urunu iceren siparis kalemleri - kalem basina bir satir (coklu urunlu siparisler icin dogru tutar)."""
    items = (
        db.query(SalesOrderItem)
        .join(SalesOrder)
        .options(
            joinedload(SalesOrderItem.product),
            joinedload(SalesOrderItem.sales_order).joinedload(SalesOrder.customer),
        )
        .filter(SalesOrderItem.product_id == product_id, SalesOrder.status != 'cancelled')
        .order_by(SalesOrder.sale_date.desc(), SalesOrderItem.id.desc())
        .all()
    )
    rows = [_serialize_item(i) for i in items]
    return [r for r in rows if r['status'] == status] if status else rows


# ---------------- Dashboard: son satislar/siparisler ----------------

def get_recent_sales(db: Session, page: int = 1, per_page: int = 5) -> dict:
    """Dashboard 'Son 10 Satis' - en yeni siparisler, sayfali."""
    base = db.query(SalesOrder).filter(SalesOrder.status != 'cancelled')
    total = base.count()
    total_pages = max(1, ceil(total / per_page))
    safe_page = min(max(1, page), total_pages)
    orders = (
        base.options(joinedload(SalesOrder.items).joinedload(SalesOrderItem.product),
                      joinedload(SalesOrder.customer))
        .order_by(SalesOrder.sale_date.desc(), SalesOrder.id.desc())
        .offset((safe_page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        'rows': [_serialize_order(o) for o in orders],
        'total': total,
        'total_pages': total_pages,
        'page': safe_page,
    }


def get_recent_orders(db: Session, limit: int = 15) -> list[dict]:
    """Dashboard 'Musteri Siparisleri' - en yeni siparisler, sayfalama yok."""
    orders = (
        db.query(SalesOrder)
        .options(joinedload(SalesOrder.items).joinedload(SalesOrderItem.product),
                 joinedload(SalesOrder.customer))
        .filter(SalesOrder.status != 'cancelled')
        .order_by(SalesOrder.sale_date.desc(), SalesOrder.id.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_order(o) for o in orders]


# ---------------- Satis trendi (genel / musteri / urun bazli) ----------------

def _daily_totals(db: Session, year: int, month: int,
                   customer_id: Optional[int] = None,
                   product_id: Optional[int] = None) -> dict[int, tuple]:
    """{gun: (tutar, adet)} - sadece veri olan gunler icin (bos gunler cagiran doldurur)."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    day_col = func.date_trunc('day', SalesOrder.sale_date).label('day')

    if product_id is not None:
        query = (
            db.query(day_col,
                     func.coalesce(func.sum(SalesOrderItem.total_price), 0),
                     func.count(SalesOrderItem.id))
            .select_from(SalesOrderItem)
            .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
            .filter(SalesOrderItem.product_id == product_id)
        )
    else:
        query = db.query(day_col, func.coalesce(func.sum(SalesOrder.total_amount), 0), func.count(SalesOrder.id))
        if customer_id is not None:
            query = query.filter(SalesOrder.customer_id == customer_id)

    query = query.filter(
        SalesOrder.status.in_(ACTIVE_STATUSES),
        SalesOrder.sale_date.between(start, end),
    ).group_by(day_col)

    result = {}
    for day, total, count in query.all():
        d = day.date() if hasattr(day, 'date') else day
        result[d.day] = (total, int(count))
    return result


def _monthly_totals(db: Session, year: int,
                     customer_id: Optional[int] = None,
                     product_id: Optional[int] = None) -> dict[int, tuple]:
    """{ay(1-12): (tutar, adet)} - o takvim yili icin."""
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    month_col = func.date_trunc('month', SalesOrder.sale_date).label('month')

    if product_id is not None:
        query = (
            db.query(month_col,
                     func.coalesce(func.sum(SalesOrderItem.total_price), 0),
                     func.count(SalesOrderItem.id))
            .select_from(SalesOrderItem)
            .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
            .filter(SalesOrderItem.product_id == product_id)
        )
    else:
        query = db.query(month_col, func.coalesce(func.sum(SalesOrder.total_amount), 0), func.count(SalesOrder.id))
        if customer_id is not None:
            query = query.filter(SalesOrder.customer_id == customer_id)

    query = query.filter(
        SalesOrder.status.in_(ACTIVE_STATUSES),
        SalesOrder.sale_date.between(start, end),
    ).group_by(month_col)

    result = {}
    for month, total, count in query.all():
        m = month.date() if hasattr(month, 'date') else month
        result[m.month] = (total, int(count))
    return result


def _yearly_totals(db: Session,
                    customer_id: Optional[int] = None,
                    product_id: Optional[int] = None) -> list[dict]:
    """Verinin kapsadigi tum yillar icin {label, sales, count} - bos yil eklenmez."""
    year_col = func.date_trunc('year', SalesOrder.sale_date).label('year')

    if product_id is not None:
        query = (
            db.query(year_col,
                     func.coalesce(func.sum(SalesOrderItem.total_price), 0),
                     func.count(SalesOrderItem.id))
            .select_from(SalesOrderItem)
            .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
            .filter(SalesOrderItem.product_id == product_id)
        )
    else:
        query = db.query(year_col, func.coalesce(func.sum(SalesOrder.total_amount), 0), func.count(SalesOrder.id))
        if customer_id is not None:
            query = query.filter(SalesOrder.customer_id == customer_id)

    query = query.filter(SalesOrder.status.in_(ACTIVE_STATUSES)).group_by(year_col).order_by(year_col)

    return [
        {'label': str((y.date() if hasattr(y, 'date') else y).year), 'sales': _money(total), 'count': int(count)}
        for y, total, count in query.all()
    ]


def get_sales_trend(db: Session, time_range: str, target: date,
                     customer_id: Optional[int] = None,
                     product_id: Optional[int] = None) -> list[dict]:
    """4 modlu satis trendi: daily | weekly | monthly | yearly.

    Genel (Dashboard), musteri bazli ve urun bazli grafikler ayni fonksiyonu
    kullanir - hangi filtrenin uygulanacagi customer_id/product_id ile secilir.
    """
    if time_range == 'yearly':
        return _yearly_totals(db, customer_id, product_id)

    if time_range == 'monthly':
        totals = _monthly_totals(db, target.year, customer_id, product_id)
        return [
            {
                'label': TURKISH_MONTHS[m - 1],
                'sales': _money(totals.get(m, (0, 0))[0]),
                'count': totals.get(m, (0, 0))[1],
            }
            for m in range(1, 13)
        ]

    # Gunluk ve haftalik: secilen ayin gun bazli toplamlarindan turetilir
    days_in_month = monthrange(target.year, target.month)[1]
    daily = _daily_totals(db, target.year, target.month, customer_id, product_id)
    full_days = [daily.get(d, (0, 0)) for d in range(1, days_in_month + 1)]

    if time_range == 'daily':
        return [
            {'label': f'{d:02d}', 'sales': _money(total), 'count': int(count)}
            for d, (total, count) in enumerate(full_days, start=1)
        ]

    # weekly: ayin gunlerini 7'serli hafta dilimlerine toplar
    weeks: list[dict] = []
    for start in range(0, days_in_month, 7):
        chunk = full_days[start:start + 7]
        sales = sum(Decimal(str(total or 0)) for total, _ in chunk)
        count = sum(c for _, c in chunk)
        weeks.append({'label': f'{len(weeks) + 1}. Hafta', 'sales': _money(sales), 'count': count})
    return weeks
