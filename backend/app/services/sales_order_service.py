"""Satis siparisi ve sevkiyat servisleri (Phase 15).

Stok hareketini yalnizca DeliveryNote yaratir. SalesOrder onayi niyet
beyanidir - stok hareketi yoktur; kismi/tam sevkiyat durumu buradan
hesaplanir.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Product, SalesOrder, SalesOrderItem
from . import uom_service

ZERO = Decimal('0')
HUNDRED = Decimal('100')


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value) -> Decimal:
    return to_decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f'Product {product_id} bulunamadi')
    return product


def line_amounts(quantity, unit_price, tax_rate) -> tuple:
    net = money(to_decimal(quantity) * to_decimal(unit_price))
    tax = money(net * to_decimal(tax_rate) / HUNDRED)
    return net, tax


def recalc_totals(doc) -> None:
    """Tutarlari kalemlerden yeniden hesaplar (frontend toplamina guvenilmez)."""
    subtotal = ZERO
    tax_total = ZERO
    for item in doc.items:
        net, tax = line_amounts(item.quantity, item.unit_price, item.tax_rate)
        item.total_price = net
        subtotal += net
        tax_total += tax
    doc.subtotal = money(subtotal)
    doc.tax_total = money(tax_total)
    doc.total_amount = money(subtotal + tax_total)


def remaining(order_item: SalesOrderItem) -> Decimal:
    """Siparis kaleminde sevkiyati bekleyen miktar, kalemin kendi biriminde."""
    return to_decimal(order_item.quantity) - to_decimal(order_item.delivered_quantity)


def to_order_uom(db: Session, order_item: SalesOrderItem, quantity, from_uom_id) -> Decimal:
    return uom_service.convert(
        db, quantity, from_uom_id, order_item.uom_id, order_item.product_id
    )


def ensure_not_over_delivery(
    db: Session, order_item: SalesOrderItem, quantity, from_uom_id
) -> None:
    """Siparis edilenden fazla sevkiyati engeller."""
    incoming = to_order_uom(db, order_item, quantity, from_uom_id)
    if incoming > remaining(order_item):
        product = db.get(Product, order_item.product_id)
        name = product.name if product else f'Product {order_item.product_id}'
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{name}" icin siparis edilenden fazla sevkiyat yapilamaz: '
                f'{incoming} istendi, kalan {remaining(order_item)}'
            ),
        )


def refresh_delivery_status(db: Session, order: SalesOrder) -> str:
    """Kalemlerin sevkiyat durumundan siparis durumunu yeniden hesaplar.

    Yalnizca YENI (Quotation/SalesOrder/DeliveryNote akisi) siparisler icin
    cagrilir - `/api/sales` uyum katmani status alanini kendi yonetir
    (`pending`/`completed`/`cancelled`), bu fonksiyon oradan cagrilmaz.
    """
    if order.status == 'cancelled':
        return order.status

    items = (
        db.query(SalesOrderItem)
        .filter(SalesOrderItem.sales_order_id == order.id)
        .all()
    )
    if not items:
        return order.status

    delivered_any = any(to_decimal(i.delivered_quantity) > ZERO for i in items)
    all_done = all(
        to_decimal(i.delivered_quantity) >= to_decimal(i.quantity) for i in items
    )
    if all_done:
        order.status = 'delivered'
    elif delivered_any:
        order.status = 'partially_delivered'
    else:
        order.status = 'confirmed'
    return order.status


def stock_quantity_for(db: Session, product: Product, quantity, uom_id) -> Decimal:
    return uom_service.to_stock_uom(db, product, quantity, uom_id)
