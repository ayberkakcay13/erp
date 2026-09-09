"""Urun yapisi servisleri: barkod dogrulama ve varyant uretimi (Phase 13)."""
import itertools
import re
import unicodedata
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    BARCODE_TYPES,
    ItemAttribute,
    ItemAttributeValue,
    Product,
    ProductBarcode,
    ProductVariantAttribute,
)


# ---------------- Barkod ----------------

def _ean_check_digit(digits: str) -> int:
    """EAN kontrol hanesi: sagdan sola 3-1-3-1... agirlikli toplamin tumleyeni."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        weight = 3 if index % 2 == 0 else 1
        total += int(char) * weight
    return (10 - total % 10) % 10


def validate_barcode(barcode: str, barcode_type: str) -> None:
    """Barkodu tipine gore dogrular; hatada 400 firlatir."""
    if barcode_type not in BARCODE_TYPES:
        raise HTTPException(status_code=400, detail=f'Gecersiz barkod tipi: {barcode_type}')

    value = (barcode or '').strip()
    if not value:
        raise HTTPException(status_code=400, detail='Barkod bos olamaz')

    if barcode_type in ('EAN13', 'EAN8'):
        length = 13 if barcode_type == 'EAN13' else 8
        if not value.isdigit() or len(value) != length:
            raise HTTPException(
                status_code=400,
                detail=f'{barcode_type} barkodu {length} haneli rakam olmali',
            )
        # Son hane kontrol hanesidir
        expected = _ean_check_digit(value[:-1])
        if int(value[-1]) != expected:
            raise HTTPException(
                status_code=400,
                detail=(
                    f'{barcode_type} kontrol hanesi hatali: '
                    f'{value[-1]} yerine {expected} olmali'
                ),
            )
    elif barcode_type == 'CODE128':
        if len(value) > 48:
            raise HTTPException(status_code=400, detail='CODE128 barkodu cok uzun')


def find_by_barcode(db: Session, barcode: str) -> ProductBarcode:
    """Barkoddan barkod kaydini bulur (RLS tenant'i zaten daraltir)."""
    row = (
        db.query(ProductBarcode)
        .filter(ProductBarcode.barcode == barcode.strip())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f'"{barcode}" barkodu bulunamadi')
    return row


# ---------------- Varyant ----------------

def slugify(value: str) -> str:
    """SKU parcasi uretir: 'Kirmizi' -> 'KIRMIZI', 'Açık Mavi' -> 'ACIK-MAVI'."""
    # Turkce karakterleri once elle esle: unicodedata 'ı' ve 'ş' icin yetersiz
    table = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
    text = value.translate(table)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-')
    return text.upper()


def generate_variants(
    db: Session,
    template: Product,
    attribute_ids: list,
    value_ids: Optional[list] = None,
) -> list:
    """Sablon urunden oznitelik kombinasyonlarini uretir.

    2 renk x 3 beden = 6 varyant. Zaten var olan kombinasyonlar atlanir,
    boylece tekrar cagrildiginda kopya urun olusmaz.
    """
    if not template.is_variant_template:
        raise HTTPException(
            status_code=400,
            detail='Bu urun varyant sablonu degil. Once is_variant_template=true yapin.',
        )
    if not attribute_ids:
        raise HTTPException(status_code=400, detail='En az bir oznitelik secilmeli')

    # Her oznitelik icin secilen degerler (verilmezse hepsi)
    per_attribute = []
    for attribute_id in attribute_ids:
        attribute = db.get(ItemAttribute, attribute_id)
        if attribute is None:
            raise HTTPException(
                status_code=404, detail=f'Oznitelik {attribute_id} bulunamadi'
            )
        query = db.query(ItemAttributeValue).filter(
            ItemAttributeValue.attribute_id == attribute_id
        )
        if value_ids:
            query = query.filter(ItemAttributeValue.id.in_(value_ids))
        values = query.order_by(ItemAttributeValue.sort_order, ItemAttributeValue.id).all()
        if not values:
            raise HTTPException(
                status_code=400,
                detail=f'"{attribute.name}" ozniteligi icin deger tanimli degil',
            )
        per_attribute.append((attribute, values))

    # Mevcut varyantlarin oznitelik imzalari - tekrar uretmemek icin
    existing_signatures = set()
    for variant in db.query(Product).filter(
        Product.parent_product_id == template.id
    ).all():
        signature = frozenset(
            (row.attribute_id, row.value_id)
            for row in db.query(ProductVariantAttribute).filter(
                ProductVariantAttribute.product_id == variant.id
            )
        )
        existing_signatures.add(signature)

    created = []
    for combination in itertools.product(*[values for _, values in per_attribute]):
        signature = frozenset(
            (value.attribute_id, value.id) for value in combination
        )
        if signature in existing_signatures:
            continue

        suffix = '-'.join(slugify(value.value) for value in combination)
        variant = Product(
            tenant_id=template.tenant_id,
            name=f'{template.name} - ' + ' / '.join(v.value for v in combination),
            sku=f'{template.sku}-{suffix}',
            price=template.price,
            stock_uom_id=template.stock_uom_id,
            purchase_uom_id=template.purchase_uom_id,
            sales_uom_id=template.sales_uom_id,
            item_group_id=template.item_group_id,
            brand_id=template.brand_id,
            product_type=template.product_type,
            is_active=True,
            description=template.description,
            is_variant_template=False,
            parent_product_id=template.id,
        )
        db.add(variant)
        db.flush()

        for value in combination:
            db.add(
                ProductVariantAttribute(
                    tenant_id=template.tenant_id,
                    product_id=variant.id,
                    attribute_id=value.attribute_id,
                    value_id=value.id,
                )
            )
        created.append(variant)
        existing_signatures.add(signature)

    db.flush()
    return created


def ensure_not_template(product: Product) -> None:
    """Sablon urune stok hareketi yazilmasini engeller.

    Sablonun ("Tisort") stogu olmaz; stok varyantlarda ("Tisort-Kirmizi-M") durur.
    """
    if product.is_variant_template:
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{product.name}" bir varyant sablonu; stok varyant urunlerde '
                'tutulur, sablonda tutulmaz.'
            ),
        )
    if product.product_type == 'hizmet':
        raise HTTPException(
            status_code=400,
            detail=f'"{product.name}" bir hizmet urunu, stok tutmaz.',
        )
