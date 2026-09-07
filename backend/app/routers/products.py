"""Product CRUD endpointleri.

Phase 10: stok artik `products` tablosunda bir kolon degil, stok defterinin
(`stock_ledger_entries`) toplami. Response'taki `stock` alani her istekte
ledger'dan hesaplanir; yazma islemleri `stock_service` uzerinden gecer.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import Product, StockLedgerEntry, User
from ..schemas import ProductCreate, ProductResponse, ProductUpdate
from ..services import stock_service

router = APIRouter(
    prefix='/api/products',
    tags=['products'],
    dependencies=[Depends(get_current_user)],
)


def _get_or_404(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f'Product {product_id} bulunamadi')
    return product


def _with_stock(db: Session, product: Product, warehouse_id: int | None = None) -> dict:
    """Urunu ledger'dan hesaplanan stok bilgisiyle birlikte dondurur."""
    return {
        'id': product.id,
        'name': product.name,
        'sku': product.sku,
        'price': product.price,
        'created_at': product.created_at,
        'stock': stock_service.get_stock(db, product.id, warehouse_id),
    }


@router.post('', response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Urunu olusturur; `stock` verilmisse acilis stok hareketi yazar."""
    product = Product(name=payload.name, sku=payload.sku, price=payload.price)
    db.add(product)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'"{payload.sku}" SKU zaten kayitli')

    opening = stock_service.to_decimal(payload.stock or 0)
    if opening > stock_service.ZERO:
        stock_service.add_entry(
            db,
            product_id=product.id,
            warehouse_id=payload.warehouse_id,
            change_qty=opening,
            reason='acilis',
            ref_type='opening',
            ref_id=product.id,
            user_id=current_user.id,
            note='Urun olusturulurken girilen acilis stogu',
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'"{payload.sku}" SKU zaten kayitli')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(product)
    return _with_stock(db, product, payload.warehouse_id)


@router.get('', response_model=list[ProductResponse])
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    warehouse_id: int | None = Query(None, description='Sadece bu deponun stogu'),
    db: Session = Depends(get_db),
):
    products = db.query(Product).order_by(Product.id).offset(skip).limit(limit).all()
    # Tek sorguda bakiye haritasi - urun basina ayri sorgu atmamak icin
    balances = stock_service.get_stock_map(
        db, [p.id for p in products], warehouse_id=warehouse_id
    )
    return [
        {
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'price': p.price,
            'created_at': p.created_at,
            'stock': balances.get(p.id, stock_service.ZERO),
        }
        for p in products
    ]


@router.get('/{product_id}', response_model=ProductResponse)
def get_product(
    product_id: int,
    warehouse_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return _with_stock(db, _get_or_404(db, product_id), warehouse_id)


@router.put('/{product_id}', response_model=ProductResponse)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Urun bilgilerini gunceller.

    `stock` gonderilirse kolon yazilmaz; hedef degere ulasmak icin fark kadar
    `duzeltme` hareketi atilir (ledger degismezligi korunur).
    """
    product = _get_or_404(db, product_id)
    data = payload.model_dump(exclude_unset=True)
    target_stock = data.pop('stock', None)
    warehouse_id = data.pop('warehouse_id', None)

    for field, value in data.items():
        setattr(product, field, value)

    if target_stock is not None:
        wh_id = stock_service.resolve_warehouse_id(db, warehouse_id)
        current = stock_service.get_stock(db, product_id, wh_id)
        diff = stock_service.to_decimal(target_stock) - current
        if diff != stock_service.ZERO:
            stock_service.add_entry(
                db,
                product_id=product_id,
                warehouse_id=wh_id,
                change_qty=diff,
                reason='duzeltme',
                ref_type='adjustment',
                ref_id=None,
                user_id=current_user.id,
                note=f'Urun guncellemesiyle stok {current} -> {target_stock}',
            )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu SKU baska bir uruncle kayitli')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(product)
    return _with_stock(db, product, warehouse_id)


@router.delete('/{product_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),  # silme sadece admin
):
    product = _get_or_404(db, product_id)
    # Stok hareketi gormus urun silinmez: defter satirlari silinemez oldugu icin
    # FK zaten engellerdi, ama hatayi anlasilir vermek daha iyi.
    has_movement = (
        db.query(StockLedgerEntry.id)
        .filter(StockLedgerEntry.product_id == product_id)
        .first()
        is not None
    )
    if has_movement:
        raise HTTPException(
            status_code=409,
            detail='Bu urunun stok hareketleri var, silinemez',
        )
    try:
        db.delete(product)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail='Bu urun bir satista kullanildigi icin silinemez',
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    return None
