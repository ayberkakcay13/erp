"""Sales endpointleri. Satis olustururken items'tan total_amount hesaplanir.

Phase 10: stok artik `products.stock` kolonuna yazilmiyor. Her satis
`stock_service.add_entry()` ile stok defterine hareket yazar:
  - satis olusturma  -> change_qty = -qty, reason='satis'
  - satis iptali     -> change_qty = +qty, reason='satis_iptal'
Ledger satirlari asla silinmez; iptal de bir hareket olarak kaydedilir.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import Customer, Product, Sale, SalesItem, User
from ..schemas import SaleCreate, SaleResponse, SaleStatusUpdate
from ..services import stock_service

router = APIRouter(
    prefix='/api/sales',
    tags=['sales'],
    dependencies=[Depends(get_current_user)],
)

CENTS = Decimal('0.01')


def _money(value) -> Decimal:
    """Tutari kurusa yuvarlar. Float'a hic ugramaz."""
    return stock_service.to_decimal(value).quantize(CENTS)


def _load_sale(db: Session, sale_id: int) -> Sale:
    """Sale'i customer + items + item.product ile birlikte yukler."""
    sale = (
        db.query(Sale)
        .options(
            joinedload(Sale.customer),
            joinedload(Sale.items).joinedload(SalesItem.product),
        )
        .filter(Sale.id == sale_id)
        .first()
    )
    if sale is None:
        raise HTTPException(status_code=404, detail=f'Sale {sale_id} bulunamadi')
    return sale


def _serialize(sale: Sale) -> dict:
    """Detayli response: musteri bilgisi + tum item'lar + urun isimleri."""
    return {
        'id': sale.id,
        'customer_id': sale.customer_id,
        'sale_date': sale.sale_date,
        'total_amount': sale.total_amount,
        'status': sale.status,
        'created_at': sale.created_at,
        'customer': sale.customer,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'total_price': item.total_price,
                'warehouse_id': item.warehouse_id,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
            }
            for item in sale.items
        ],
    }


def _requested_by_product_warehouse(db: Session, items) -> dict:
    """Satis kalemlerini (urun, depo) kirilimda toplar.

    Ayni urun birden fazla satirda olabilir; stok kontrolu ve ledger hareketi
    toplam miktar uzerinden yapilir.
    """
    totals: dict[tuple[int, int], Decimal] = {}
    for item in items:
        wh_id = stock_service.resolve_warehouse_id(db, getattr(item, 'warehouse_id', None))
        key = (item.product_id, wh_id)
        totals[key] = totals.get(key, stock_service.ZERO) + stock_service.to_decimal(
            item.quantity
        )
    return totals


@router.post('', response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: SaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=404, detail=f'Customer {payload.customer_id} bulunamadi'
        )

    # Once tum urunleri dogrula, sonra kayit ac - yarim satis olusmasin
    for item in payload.items:
        if db.get(Product, item.product_id) is None:
            raise HTTPException(
                status_code=404, detail=f'Product {item.product_id} bulunamadi'
            )

    requested = _requested_by_product_warehouse(db, payload.items)

    # Stok kontrolu: yetersizse hicbir kayit olusmadan 400 don
    for (product_id, wh_id), quantity in requested.items():
        if not stock_service.check_availability(db, product_id, wh_id, quantity):
            product = db.get(Product, product_id)
            available = stock_service.get_stock(db, product_id, wh_id)
            raise HTTPException(
                status_code=400,
                detail=(
                    f'"{product.name}" icin stok yetersiz: '
                    f'{quantity} adet istendi, stokta {available} adet var'
                ),
            )

    sale = Sale(
        customer_id=payload.customer_id,
        sale_date=payload.sale_date or date.today(),
        total_amount=stock_service.ZERO,
        status='pending',
    )

    total = stock_service.ZERO
    for item in payload.items:
        qty = stock_service.to_decimal(item.quantity)
        unit_price = stock_service.to_decimal(item.unit_price)
        line_total = _money(qty * unit_price)
        total += line_total
        sale.items.append(
            SalesItem(
                product_id=item.product_id,
                quantity=qty,
                unit_price=unit_price,
                total_price=line_total,
                warehouse_id=stock_service.resolve_warehouse_id(db, item.warehouse_id),
            )
        )
    sale.total_amount = _money(total)

    db.add(sale)
    db.flush()  # sale.id ledger ref_id olarak lazim

    # Stok dusur - satis kaydiyla ayni transaction'da, commit birlikte
    for (product_id, wh_id), quantity in requested.items():
        stock_service.add_entry(
            db,
            product_id=product_id,
            warehouse_id=wh_id,
            change_qty=-quantity,
            reason='satis',
            ref_type='sale',
            ref_id=sale.id,
            user_id=current_user.id,
        )

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Satis kaydedilemedi: {exc}')

    return _serialize(_load_sale(db, sale.id))


@router.get('', response_model=list[SaleResponse])
def list_sales(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    customer_id: int | None = Query(None, description='Musteriye gore filtrele'),
    db: Session = Depends(get_db),
):
    query = db.query(Sale).options(
        joinedload(Sale.customer),
        joinedload(Sale.items).joinedload(SalesItem.product),
    )
    if customer_id is not None:
        query = query.filter(Sale.customer_id == customer_id)
    sales = query.order_by(Sale.id).offset(skip).limit(limit).all()
    return [_serialize(sale) for sale in sales]


@router.get('/{sale_id}', response_model=SaleResponse)
def get_sale(sale_id: int, db: Session = Depends(get_db)):
    """Satistan sonra bilgi cekme: musteri + items + urun isimleri dahil."""
    return _serialize(_load_sale(db, sale_id))


def _item_totals(db: Session, sale: Sale) -> dict:
    """Satistaki (urun, depo) basina toplam miktar."""
    return _requested_by_product_warehouse(db, sale.items)


@router.put('/{sale_id}', response_model=SaleResponse)
def update_sale_status(
    sale_id: int,
    payload: SaleStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Satis durumunu gunceller ve stogu duruma gore geri ekler/yeniden duser.

    Stok mantigi: "cancelled" disindaki her durumda satis stogu tutuyor sayilir.
    - cancelled disi -> cancelled : ledger'a +qty (`satis_iptal`)
    - cancelled -> cancelled disi : ledger'a -qty (`satis`), yetersizse 400
    - ayni gruptaki gecisler (pending <-> completed) stogu etkilemez

    Durum degismiyorsa hicbir stok hareketi olmaz, bu sayede ayni istegi
    tekrarlamak stogu ikinci kez degistirmez (idempotent).
    """
    sale = _load_sale(db, sale_id)
    old_status = sale.status
    new_status = payload.status

    was_cancelled = old_status == 'cancelled'
    will_be_cancelled = new_status == 'cancelled'

    # Stok yalnizca "iptal" sinirini gecerken hareket eder
    restore_stock = not was_cancelled and will_be_cancelled
    deduct_stock = was_cancelled and not will_be_cancelled

    totals = _item_totals(db, sale) if (restore_stock or deduct_stock) else {}

    if deduct_stock:
        # Iptal geri alindi: stok yeniden dusulecek, once yeterli mi kontrol et
        for (product_id, wh_id), quantity in totals.items():
            product = db.get(Product, product_id)
            if product is None:
                raise HTTPException(
                    status_code=404,
                    detail=f'Product {product_id} bulunamadi, satis geri alinamiyor',
                )
            if not stock_service.check_availability(db, product_id, wh_id, quantity):
                available = stock_service.get_stock(db, product_id, wh_id)
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f'Iptal geri alinamiyor: "{product.name}" icin stok yetersiz. '
                        f'{quantity} adet gerekli, stokta {available} adet var'
                    ),
                )

    for (product_id, wh_id), quantity in totals.items():
        stock_service.add_entry(
            db,
            product_id=product_id,
            warehouse_id=wh_id,
            change_qty=quantity if restore_stock else -quantity,
            reason='satis_iptal' if restore_stock else 'satis',
            ref_type='sale',
            ref_id=sale.id,
            user_id=current_user.id,
            note=f'Satis durumu {old_status} -> {new_status}',
        )

    sale.status = new_status
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Durum guncellenemedi: {exc}')
    return _serialize(_load_sale(db, sale_id))
