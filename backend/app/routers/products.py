"""Product CRUD endpointleri.

Phase 10: stok artik `products` tablosunda bir kolon degil, stok defterinin
(`stock_ledger_entries`) toplami. Response'taki `stock` alani her istekte
ledger'dan hesaplanir; yazma islemleri `stock_service` uzerinden gecer.

Phase 13: urun karti genisledi (olcu birimi, kategori, marka, barkod,
varyant). Stok DAIMA urunun `stock_uom` biriminde tutulur; farkli birimde
girilen miktar ledger'a yazilmadan once `uom_service` ile cevrilir.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import Product, ProductBarcode, StockLedgerEntry, User
from ..schemas import (
    GenerateVariantsRequest,
    ProductBarcodeCreate,
    ProductBarcodeResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from ..services import product_service, stock_service, uom_service

router = APIRouter(
    prefix='/api/products',
    tags=['products'],
    dependencies=[Depends(get_current_user)],
)

# Urun kartinin dogrudan yazilabilir alanlari (stok ve barkodlar ayri islenir)
CARD_FIELDS = (
    'name', 'sku', 'price', 'stock_uom_id', 'purchase_uom_id', 'sales_uom_id',
    'item_group_id', 'brand_id', 'product_type', 'is_active', 'description',
    'image_url', 'min_stock_level', 'max_stock_level', 'is_variant_template',
    'parent_product_id',
)


def _load(db: Session, product_id: int) -> Product:
    product = (
        db.query(Product)
        .options(
            joinedload(Product.barcodes),
            joinedload(Product.stock_uom),
            joinedload(Product.item_group),
            joinedload(Product.brand),
        )
        .filter(Product.id == product_id)
        .first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail=f'Product {product_id} bulunamadi')
    return product


def _serialize(product: Product, stock) -> dict:
    return {
        'id': product.id,
        'name': product.name,
        'sku': product.sku,
        'price': product.price,
        'created_at': product.created_at,
        'stock': stock,
        'stock_uom_id': product.stock_uom_id,
        'purchase_uom_id': product.purchase_uom_id,
        'sales_uom_id': product.sales_uom_id,
        'item_group_id': product.item_group_id,
        'brand_id': product.brand_id,
        'product_type': product.product_type,
        'is_active': product.is_active,
        'description': product.description,
        'image_url': product.image_url,
        'min_stock_level': product.min_stock_level,
        'max_stock_level': product.max_stock_level,
        'is_variant_template': product.is_variant_template,
        'parent_product_id': product.parent_product_id,
        'stock_uom_code': product.stock_uom.code if product.stock_uom else None,
        'item_group_name': product.item_group.name if product.item_group else None,
        'brand_name': product.brand.name if product.brand else None,
        'barcodes': [
            {
                'id': b.id, 'product_id': b.product_id, 'barcode': b.barcode,
                'barcode_type': b.barcode_type, 'uom_id': b.uom_id,
                'is_primary': b.is_primary,
            }
            for b in product.barcodes
        ],
    }


def _with_stock(db: Session, product: Product, warehouse_id: int | None = None) -> dict:
    return _serialize(product, stock_service.get_stock(db, product.id, warehouse_id))


def _add_barcodes(db: Session, product: Product, barcodes) -> None:
    for entry in barcodes:
        product_service.validate_barcode(entry.barcode, entry.barcode_type)
        db.add(
            ProductBarcode(
                product_id=product.id,
                barcode=entry.barcode.strip(),
                barcode_type=entry.barcode_type,
                uom_id=entry.uom_id,
                is_primary=entry.is_primary,
            )
        )


@router.post('', response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Urunu olusturur; `stock` verilmisse acilis stok hareketi yazar."""
    data = payload.model_dump()
    product = Product(**{field: data[field] for field in CARD_FIELDS if field in data})
    db.add(product)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'"{payload.sku}" SKU zaten kayitli')

    _add_barcodes(db, product, payload.barcodes)

    opening = stock_service.to_decimal(payload.stock or 0)
    if opening > stock_service.ZERO:
        # Phase 13: girilen miktar farkli birimdeyse once stok birimine cevir
        opening = uom_service.to_stock_uom(
            db, product, opening, payload.stock_entry_uom_id
        )
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
        raise HTTPException(
            status_code=409,
            detail=f'"{payload.sku}" SKU ya da barkodlardan biri zaten kayitli',
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    return _with_stock(db, _load(db, product.id), payload.warehouse_id)


@router.get('', response_model=list[ProductResponse])
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    warehouse_id: int | None = Query(None, description='Sadece bu deponun stogu'),
    item_group_id: int | None = Query(None),
    brand_id: int | None = Query(None),
    product_type: str | None = Query(None),
    include_templates: bool = Query(True, description='Varyant sablonlarini da getir'),
    db: Session = Depends(get_db),
):
    query = db.query(Product).options(
        joinedload(Product.barcodes),
        joinedload(Product.stock_uom),
        joinedload(Product.item_group),
        joinedload(Product.brand),
    )
    if item_group_id is not None:
        query = query.filter(Product.item_group_id == item_group_id)
    if brand_id is not None:
        query = query.filter(Product.brand_id == brand_id)
    if product_type is not None:
        query = query.filter(Product.product_type == product_type)
    if not include_templates:
        query = query.filter(Product.is_variant_template.is_(False))

    products = query.order_by(Product.id).offset(skip).limit(limit).all()
    # Tek sorguda bakiye haritasi - urun basina ayri sorgu atmamak icin
    balances = stock_service.get_stock_map(
        db, [p.id for p in products], warehouse_id=warehouse_id
    )
    return [
        _serialize(p, balances.get(p.id, stock_service.ZERO)) for p in products
    ]


@router.get('/by-barcode/{barcode}')
def get_by_barcode(barcode: str, db: Session = Depends(get_db)):
    """Barkoddan urun + birim bulur. Barkod okuyucu bu endpoint'i cagirir."""
    row = product_service.find_by_barcode(db, barcode)
    product = _load(db, row.product_id)
    return {
        'barcode': row.barcode,
        'barcode_type': row.barcode_type,
        'uom_id': row.uom_id,
        # Okuyucudan gelen barkod hangi birimi gosteriyor - kasa ekraninda
        # "1 koli" mi "1 adet" mi okundugu ayirt edilebilsin
        'uom_code': row.uom.code if row.uom else None,
        'is_primary': row.is_primary,
        'product': _with_stock(db, product),
    }


@router.get('/{product_id}', response_model=ProductResponse)
def get_product(
    product_id: int,
    warehouse_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return _with_stock(db, _load(db, product_id), warehouse_id)


@router.get('/{product_id}/variants', response_model=list[ProductResponse])
def list_variants(product_id: int, db: Session = Depends(get_db)):
    """Sablon urunun varyantlari. Stok varyant seviyesinde tutulur."""
    _load(db, product_id)
    variants = (
        db.query(Product)
        .options(joinedload(Product.barcodes), joinedload(Product.stock_uom),
                 joinedload(Product.item_group), joinedload(Product.brand))
        .filter(Product.parent_product_id == product_id)
        .order_by(Product.sku)
        .all()
    )
    balances = stock_service.get_stock_map(db, [v.id for v in variants])
    return [_serialize(v, balances.get(v.id, stock_service.ZERO)) for v in variants]


@router.post(
    '/{product_id}/generate-variants',
    response_model=list[ProductResponse],
    status_code=status.HTTP_201_CREATED,
)
def generate_variants(
    product_id: int,
    payload: GenerateVariantsRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Secilen ozniteliklerin kombinasyonundan varyant urunleri uretir.

    2 renk x 3 beden = 6 varyant. Tekrar cagrilirsa var olanlar atlanir.
    """
    template = _load(db, product_id)
    created = product_service.generate_variants(
        db, template, payload.attribute_ids, payload.value_ids
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail='Uretilen varyant SKU\'lardan biri zaten kayitli'
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Varyantlar uretilemedi: {exc}')

    return [
        _serialize(_load(db, variant.id), stock_service.ZERO) for variant in created
    ]


@router.post(
    '/{product_id}/barcodes',
    response_model=ProductBarcodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_barcode(
    product_id: int,
    payload: ProductBarcodeCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    product = _load(db, product_id)
    _add_barcodes(db, product, [payload])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f'"{payload.barcode}" barkodu zaten kayitli'
        )
    return (
        db.query(ProductBarcode)
        .filter(
            ProductBarcode.product_id == product_id,
            ProductBarcode.barcode == payload.barcode.strip(),
        )
        .first()
    )


@router.delete(
    '/{product_id}/barcodes/{barcode_id}', status_code=status.HTTP_204_NO_CONTENT
)
def delete_barcode(
    product_id: int,
    barcode_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = db.get(ProductBarcode, barcode_id)
    if row is None or row.product_id != product_id:
        raise HTTPException(status_code=404, detail=f'Barkod {barcode_id} bulunamadi')
    db.delete(row)
    db.commit()
    return None


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
    product = _load(db, product_id)
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
    return _with_stock(db, _load(db, product_id), warehouse_id)


@router.delete('/{product_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),  # silme sadece admin
):
    product = _load(db, product_id)
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
    if db.query(Product.id).filter(Product.parent_product_id == product_id).first():
        raise HTTPException(
            status_code=409, detail='Varyantlari olan sablon urun silinemez'
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
