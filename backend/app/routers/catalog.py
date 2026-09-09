"""Urun yapisi endpointleri (Phase 13): olcu birimi, kategori, marka, oznitelik.

Hepsi ayni dosyada cunku hepsi urun kartinin yardimci tablolari; ayri
router dosyalarina bolmek okumayi kolaylastirmiyor.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import (
    UOM,
    Brand,
    ItemAttribute,
    ItemAttributeValue,
    ItemGroup,
    Product,
    UOMConversion,
    User,
)
from ..schemas import (
    BrandCreate,
    BrandResponse,
    BrandUpdate,
    ItemAttributeCreate,
    ItemAttributeResponse,
    ItemAttributeValueCreate,
    ItemAttributeValueResponse,
    ItemGroupCreate,
    ItemGroupResponse,
    ItemGroupUpdate,
    UOMConversionCreate,
    UOMConversionResponse,
    UOMCreate,
    UOMResponse,
    UOMUpdate,
)
from ..services import uom_service
from ..services.tenant_context import current_tenant_id

# ---------------- Olcu birimi ----------------

uom_router = APIRouter(
    prefix='/api/uoms',
    tags=['uoms'],
    dependencies=[Depends(get_current_user)],
)


def _get_uom(db: Session, uom_id: int) -> UOM:
    uom = db.get(UOM, uom_id)
    if uom is None:
        raise HTTPException(status_code=404, detail=f'Olcu birimi {uom_id} bulunamadi')
    return uom


@uom_router.post('', response_model=UOMResponse, status_code=status.HTTP_201_CREATED)
def create_uom(
    payload: UOMCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    uom = UOM(**payload.model_dump())
    db.add(uom)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'"{payload.code}" birimi zaten kayitli')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Veritabani hatasi: {exc}')
    db.refresh(uom)
    return uom


@uom_router.get('', response_model=list[UOMResponse])
def list_uoms(
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(UOM)
    if is_active is not None:
        query = query.filter(UOM.is_active.is_(is_active))
    return query.order_by(UOM.code).all()


@uom_router.post('/ensure-defaults', response_model=list[UOMResponse])
def ensure_default_uoms(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Varsayilan birimleri ve evrensel donusumleri kurar (idempotent)."""
    uom_service.ensure_defaults(db, current_tenant_id.get())
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Birimler kurulamadi: {exc}')
    return db.query(UOM).order_by(UOM.code).all()


@uom_router.put('/{uom_id}', response_model=UOMResponse)
def update_uom(
    uom_id: int,
    payload: UOMUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    uom = _get_uom(db, uom_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(uom, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu birim kodu zaten kayitli')
    db.refresh(uom)
    return uom


@uom_router.delete('/{uom_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_uom(
    uom_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    uom = _get_uom(db, uom_id)
    in_use = db.query(Product.id).filter(
        (Product.stock_uom_id == uom_id)
        | (Product.purchase_uom_id == uom_id)
        | (Product.sales_uom_id == uom_id)
    ).first()
    if in_use:
        raise HTTPException(
            status_code=409, detail='Bu birim urunlerde kullaniliyor, silinemez'
        )
    db.delete(uom)
    db.commit()
    return None


# ---------------- Birim donusumu ----------------

conversion_router = APIRouter(
    prefix='/api/uom-conversions',
    tags=['uoms'],
    dependencies=[Depends(get_current_user)],
)


def _serialize_conversion(row: UOMConversion) -> dict:
    return {
        'id': row.id,
        'from_uom_id': row.from_uom_id,
        'to_uom_id': row.to_uom_id,
        'factor': row.factor,
        'product_id': row.product_id,
        'from_uom_code': row.from_uom.code if row.from_uom else None,
        'to_uom_code': row.to_uom.code if row.to_uom else None,
    }


@conversion_router.post(
    '', response_model=UOMConversionResponse, status_code=status.HTTP_201_CREATED
)
def create_conversion(
    payload: UOMConversionCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Donusum ekler. `product_id` doluysa o urune ozeldir ve geneli ezer."""
    if payload.from_uom_id == payload.to_uom_id:
        raise HTTPException(status_code=400, detail='Kaynak ve hedef birim ayni olamaz')
    _get_uom(db, payload.from_uom_id)
    _get_uom(db, payload.to_uom_id)
    if payload.product_id is not None and db.get(Product, payload.product_id) is None:
        raise HTTPException(
            status_code=404, detail=f'Product {payload.product_id} bulunamadi'
        )

    conversion = UOMConversion(**payload.model_dump())
    db.add(conversion)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu donusum zaten tanimli')
    db.refresh(conversion)
    return _serialize_conversion(conversion)


@conversion_router.get('', response_model=list[UOMConversionResponse])
def list_conversions(
    product_id: int | None = Query(None, description='Urune ozel donusumler'),
    db: Session = Depends(get_db),
):
    query = db.query(UOMConversion).options(
        joinedload(UOMConversion.from_uom), joinedload(UOMConversion.to_uom)
    )
    if product_id is not None:
        query = query.filter(UOMConversion.product_id == product_id)
    return [_serialize_conversion(r) for r in query.order_by(UOMConversion.id).all()]


@conversion_router.get('/convert')
def preview_conversion(
    quantity: str = Query(..., description='Cevrilecek miktar'),
    from_uom_id: int = Query(...),
    to_uom_id: int = Query(...),
    product_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Donusum onizlemesi - form doldururken kullanicinin gormesi icin."""
    result = uom_service.convert(db, quantity, from_uom_id, to_uom_id, product_id)
    return {
        'quantity': uom_service.to_decimal(quantity),
        'from_uom_id': from_uom_id,
        'to_uom_id': to_uom_id,
        'product_id': product_id,
        'converted': result,
    }


@conversion_router.delete('/{conversion_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_conversion(
    conversion_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    conversion = db.get(UOMConversion, conversion_id)
    if conversion is None:
        raise HTTPException(status_code=404, detail=f'Donusum {conversion_id} bulunamadi')
    db.delete(conversion)
    db.commit()
    return None


# ---------------- Kategori (agac) ----------------

group_router = APIRouter(
    prefix='/api/item-groups',
    tags=['item-groups'],
    dependencies=[Depends(get_current_user)],
)


def _get_group(db: Session, group_id: int) -> ItemGroup:
    group = db.get(ItemGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f'Kategori {group_id} bulunamadi')
    return group


def _check_group_parent(db: Session, group_id: int | None, parent_id: int | None) -> None:
    """Bir grup kendi alt grubunu ust grup olarak secemez (dongu olusur)."""
    if parent_id is None:
        return
    if group_id is not None and parent_id == group_id:
        raise HTTPException(status_code=400, detail='Kategori kendi ust kategorisi olamaz')
    parent = db.get(ItemGroup, parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail=f'Ust kategori {parent_id} bulunamadi')

    seen = {group_id} if group_id is not None else set()
    cursor = parent
    while cursor is not None:
        if cursor.id in seen:
            raise HTTPException(
                status_code=400, detail='Kategori agacinda dongu olusuyor'
            )
        seen.add(cursor.id)
        cursor = db.get(ItemGroup, cursor.parent_id) if cursor.parent_id else None


@group_router.post('', response_model=ItemGroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: ItemGroupCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    _check_group_parent(db, None, payload.parent_id)
    group = ItemGroup(**payload.model_dump())
    db.add(group)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f'"{payload.code}" kategori kodu zaten kayitli'
        )
    db.refresh(group)
    return group


@group_router.get('', response_model=list[ItemGroupResponse])
def list_groups(db: Session = Depends(get_db)):
    return db.query(ItemGroup).order_by(ItemGroup.name).all()


@group_router.get('/tree')
def group_tree(db: Session = Depends(get_db)):
    """Kategorileri ic ice agac olarak doner."""
    groups = db.query(ItemGroup).order_by(ItemGroup.name).all()
    nodes = {
        g.id: {
            'id': g.id, 'code': g.code, 'name': g.name,
            'parent_id': g.parent_id, 'is_active': g.is_active, 'children': [],
        }
        for g in groups
    }
    roots = []
    for group in groups:
        node = nodes[group.id]
        parent = nodes.get(group.parent_id)
        if parent is None:
            roots.append(node)
        else:
            parent['children'].append(node)
    return roots


@group_router.put('/{group_id}', response_model=ItemGroupResponse)
def update_group(
    group_id: int,
    payload: ItemGroupUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    group = _get_group(db, group_id)
    data = payload.model_dump(exclude_unset=True)
    if 'parent_id' in data:
        _check_group_parent(db, group_id, data['parent_id'])
    for field, value in data.items():
        setattr(group, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu kategori kodu zaten kayitli')
    db.refresh(group)
    return group


@group_router.delete('/{group_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Alt grubu ya da urunu olan kategori silinemez."""
    _get_group(db, group_id)
    if db.query(ItemGroup.id).filter(ItemGroup.parent_id == group_id).first():
        raise HTTPException(
            status_code=400, detail='Alt kategorisi olan kategori silinemez'
        )
    if db.query(Product.id).filter(Product.item_group_id == group_id).first():
        raise HTTPException(status_code=400, detail='Urunu olan kategori silinemez')
    db.delete(db.get(ItemGroup, group_id))
    db.commit()
    return None


# ---------------- Marka ----------------

brand_router = APIRouter(
    prefix='/api/brands',
    tags=['brands'],
    dependencies=[Depends(get_current_user)],
)


@brand_router.post('', response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
def create_brand(
    payload: BrandCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    brand = Brand(**payload.model_dump())
    db.add(brand)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'"{payload.name}" markasi zaten var')
    db.refresh(brand)
    return brand


@brand_router.get('', response_model=list[BrandResponse])
def list_brands(db: Session = Depends(get_db)):
    return db.query(Brand).order_by(Brand.name).all()


@brand_router.put('/{brand_id}', response_model=BrandResponse)
def update_brand(
    brand_id: int,
    payload: BrandUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise HTTPException(status_code=404, detail=f'Marka {brand_id} bulunamadi')
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu marka adi zaten kayitli')
    db.refresh(brand)
    return brand


@brand_router.delete('/{brand_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise HTTPException(status_code=404, detail=f'Marka {brand_id} bulunamadi')
    if db.query(Product.id).filter(Product.brand_id == brand_id).first():
        raise HTTPException(status_code=400, detail='Urunu olan marka silinemez')
    db.delete(brand)
    db.commit()
    return None


# ---------------- Varyant oznitelikleri ----------------

attribute_router = APIRouter(
    prefix='/api/item-attributes',
    tags=['item-attributes'],
    dependencies=[Depends(get_current_user)],
)


def _serialize_attribute(attribute: ItemAttribute) -> dict:
    return {
        'id': attribute.id,
        'name': attribute.name,
        'values': [
            {
                'id': v.id, 'attribute_id': v.attribute_id,
                'value': v.value, 'sort_order': v.sort_order,
            }
            for v in sorted(attribute.values, key=lambda v: (v.sort_order, v.id))
        ],
    }


@attribute_router.post(
    '', response_model=ItemAttributeResponse, status_code=status.HTTP_201_CREATED
)
def create_attribute(
    payload: ItemAttributeCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    attribute = ItemAttribute(name=payload.name)
    for value in payload.values:
        attribute.values.append(
            ItemAttributeValue(value=value.value, sort_order=value.sort_order)
        )
    db.add(attribute)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f'"{payload.name}" ozniteligi zaten var'
        )
    db.refresh(attribute)
    return _serialize_attribute(attribute)


@attribute_router.get('', response_model=list[ItemAttributeResponse])
def list_attributes(db: Session = Depends(get_db)):
    rows = (
        db.query(ItemAttribute)
        .options(joinedload(ItemAttribute.values))
        .order_by(ItemAttribute.name)
        .all()
    )
    return [_serialize_attribute(a) for a in rows]


@attribute_router.post(
    '/{attribute_id}/values',
    response_model=ItemAttributeValueResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_attribute_value(
    attribute_id: int,
    payload: ItemAttributeValueCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    attribute = db.get(ItemAttribute, attribute_id)
    if attribute is None:
        raise HTTPException(status_code=404, detail=f'Oznitelik {attribute_id} bulunamadi')
    value = ItemAttributeValue(
        attribute_id=attribute_id, value=payload.value, sort_order=payload.sort_order
    )
    db.add(value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu deger zaten tanimli')
    db.refresh(value)
    return value


@attribute_router.delete(
    '/{attribute_id}', status_code=status.HTTP_204_NO_CONTENT
)
def delete_attribute(
    attribute_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    attribute = db.get(ItemAttribute, attribute_id)
    if attribute is None:
        raise HTTPException(status_code=404, detail=f'Oznitelik {attribute_id} bulunamadi')
    db.delete(attribute)
    db.commit()
    return None
