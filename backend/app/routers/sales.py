"""Sales endpointleri. Satis olustururken items'tan total_amount hesaplanir."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Customer, Product, Sale, SalesItem
from ..schemas import SaleCreate, SaleResponse, SaleStatusUpdate

router = APIRouter(prefix='/api/sales', tags=['sales'])


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
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
            }
            for item in sale.items
        ],
    }


@router.post('', response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def create_sale(payload: SaleCreate, db: Session = Depends(get_db)):
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=404, detail=f'Customer {payload.customer_id} bulunamadi'
        )

    # Once tum urunleri dogrula, sonra kayit ac - yarim satis olusmasin
    products = {}
    for item in payload.items:
        if item.product_id not in products:
            product = db.get(Product, item.product_id)
            if product is None:
                raise HTTPException(
                    status_code=404, detail=f'Product {item.product_id} bulunamadi'
                )
            products[item.product_id] = product

    sale = Sale(
        customer_id=payload.customer_id,
        sale_date=payload.sale_date or date.today(),
        total_amount=0.0,
        status='pending',
    )

    total = 0.0
    for item in payload.items:
        line_total = round(item.quantity * item.unit_price, 2)
        total += line_total
        sale.items.append(
            SalesItem(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=line_total,
            )
        )
    sale.total_amount = round(total, 2)

    db.add(sale)
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


@router.put('/{sale_id}', response_model=SaleResponse)
def update_sale_status(
    sale_id: int, payload: SaleStatusUpdate, db: Session = Depends(get_db)
):
    sale = _load_sale(db, sale_id)
    sale.status = payload.status
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Durum guncellenemedi: {exc}')
    return _serialize(_load_sale(db, sale_id))
