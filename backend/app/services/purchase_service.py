"""Satin alma servisleri (Phase 14).

Stok hareketini yalnizca mal kabul yaratir. Siparis niyet beyanidir, fatura
mali belgedir - ikisi de ledger'a dokunmaz.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    Product,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    Supplier,
    Warehouse,
)
from . import stock_service, uom_service

ZERO = Decimal('0')
HUNDRED = Decimal('100')


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value) -> Decimal:
    return to_decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail=f'Tedarikci {supplier_id} bulunamadi')
    return supplier


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f'Product {product_id} bulunamadi')
    return product


def resolve_warehouse_id(db: Session, warehouse_id: Optional[int]) -> int:
    return stock_service.resolve_warehouse_id(db, warehouse_id)


def line_amounts(quantity, unit_price, tax_rate) -> tuple:
    """Satirin (net tutar, vergi tutari) ikilisini doner."""
    net = money(to_decimal(quantity) * to_decimal(unit_price))
    tax = money(net * to_decimal(tax_rate) / HUNDRED)
    return net, tax


def recalc_totals(doc) -> None:
    """Tutarlari kalemlerden yeniden hesaplar.

    Frontend'den gelen toplama guvenilmez; hesap her zaman burada yapilir.
    """
    subtotal = ZERO
    tax_total = ZERO
    for item in doc.items:
        net, tax = line_amounts(item.quantity, item.unit_price, item.tax_rate)
        item.line_total = net
        subtotal += net
        tax_total += tax
    doc.subtotal = money(subtotal)
    doc.tax_total = money(tax_total)
    doc.grand_total = money(subtotal + tax_total)


def remaining(order_item: PurchaseOrderItem) -> Decimal:
    """Siparis kaleminde teslim alinmayi bekleyen miktar, kalemin kendi biriminde."""
    return to_decimal(order_item.quantity) - to_decimal(order_item.received_quantity)


def to_order_uom(db: Session, order_item: PurchaseOrderItem, quantity, from_uom_id) -> Decimal:
    return uom_service.convert(
        db, quantity, from_uom_id, order_item.uom_id, order_item.product_id
    )


def ensure_not_over_receipt(
    db: Session, order_item: PurchaseOrderItem, quantity, from_uom_id, exclude_item_id=None
) -> None:
    """Siparis edilenden fazla kabulu engeller."""
    incoming = to_order_uom(db, order_item, quantity, from_uom_id)
    pending = pending_draft_quantity(db, order_item, exclude_item_id)
    if incoming + pending > remaining(order_item):
        product = db.get(Product, order_item.product_id)
        name = product.name if product else f'Product {order_item.product_id}'
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{name}" icin siparis edilenden fazla kabul edilemez: '
                f'{incoming} istendi, kalan {remaining(order_item) - pending}'
            ),
        )


def pending_draft_quantity(
    db: Session, order_item: PurchaseOrderItem, exclude_item_id=None
) -> Decimal:
    """Onaylanmamis mal kabullerde bu siparis kalemi icin bekleyen miktar."""
    query = (
        db.query(PurchaseReceiptItem)
        .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseReceiptItem.purchase_receipt_id)
        .filter(
            PurchaseReceiptItem.purchase_order_item_id == order_item.id,
            PurchaseReceipt.docstatus == 0,
        )
    )
    if exclude_item_id is not None:
        query = query.filter(PurchaseReceiptItem.id != exclude_item_id)
    total = ZERO
    for item in query.all():
        total += to_order_uom(db, order_item, item.accepted_quantity, item.uom_id)
    return total


def stock_quantity_for(db: Session, product: Product, quantity, uom_id) -> Decimal:
    return uom_service.to_stock_uom(db, product, quantity, uom_id)


def unit_cost_for(quantity, unit_price, stock_quantity) -> Optional[Decimal]:
    stock_qty = to_decimal(stock_quantity)
    if stock_qty == ZERO:
        return None
    return money(to_decimal(quantity) * to_decimal(unit_price) / stock_qty)


def apply_receipt(db: Session, receipt: PurchaseReceipt, sign: int, user_id=None) -> None:
    """Mal kabulun stok ve siparis yan etkilerini uygular (sign=1 onay, -1 iptal)."""
    reason = 'alim' if sign > 0 else 'alim_iade'
    note = 'Mal kabul onaylandi' if sign > 0 else 'Mal kabul iptal edildi'
    warehouse_id = resolve_warehouse_id(db, receipt.warehouse_id)

    touched_orders = {}
    for item in receipt.items:
        accepted = to_decimal(item.accepted_quantity)
        if accepted == ZERO:
            continue

        stock_qty = to_decimal(item.stock_quantity)
        if stock_qty == ZERO:
            product = get_product(db, item.product_id)
            stock_qty = stock_quantity_for(db, product, accepted, item.uom_id)
            item.stock_quantity = stock_qty

        stock_service.add_entry(
            db,
            product_id=item.product_id,
            warehouse_id=warehouse_id,
            change_qty=sign * stock_qty,
            reason=reason,
            ref_type='purchase',
            ref_id=receipt.id,
            user_id=user_id,
            note=note,
            unit_cost=unit_cost_for(accepted, item.unit_price, stock_qty),
        )

        if item.purchase_order_item_id is None:
            continue
        order_item = db.get(PurchaseOrderItem, item.purchase_order_item_id)
        if order_item is None:
            continue
        delta = to_order_uom(db, order_item, accepted, item.uom_id)
        order_item.received_quantity = (
            to_decimal(order_item.received_quantity) + sign * delta
        )
        touched_orders[order_item.purchase_order_id] = True

    if receipt.purchase_order_id is not None:
        touched_orders[receipt.purchase_order_id] = True

    db.flush()
    for order_id in touched_orders:
        order = db.get(PurchaseOrder, order_id)
        if order is not None:
            refresh_order_status(db, order)


def refresh_order_status(db: Session, order: PurchaseOrder) -> str:
    """Kalemlerin teslim durumundan siparis durumunu yeniden hesaplar."""
    if order.status == 'iptal':
        return order.status

    items = (
        db.query(PurchaseOrderItem)
        .filter(PurchaseOrderItem.purchase_order_id == order.id)
        .all()
    )
    if not items:
        order.status = 'beklemede'
        return order.status

    received_any = any(to_decimal(i.received_quantity) > ZERO for i in items)
    all_done = all(
        to_decimal(i.received_quantity) >= to_decimal(i.quantity) for i in items
    )
    if all_done:
        order.status = 'tamamlandi'
    elif received_any:
        order.status = 'kismi_teslim'
    else:
        order.status = 'beklemede'
    return order.status


def due_date_for(supplier: Supplier, invoice_date: date) -> date:
    return invoice_date + timedelta(days=supplier.payment_term_days or 0)


def three_way_match(db: Session, order: PurchaseOrder) -> dict:
    """Siparis / mal kabul / fatura karsilastirmasi."""
    receipt_items = (
        db.query(PurchaseReceiptItem)
        .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseReceiptItem.purchase_receipt_id)
        .filter(
            PurchaseReceipt.purchase_order_id == order.id,
            PurchaseReceipt.docstatus == 1,
        )
        .all()
    )
    invoice_items = (
        db.query(PurchaseInvoiceItem)
        .join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceItem.purchase_invoice_id)
        .join(
            PurchaseReceipt,
            PurchaseReceipt.id == PurchaseInvoice.purchase_receipt_id,
        )
        .filter(
            PurchaseReceipt.purchase_order_id == order.id,
            PurchaseInvoice.docstatus == 1,
        )
        .all()
    )

    rows = []
    has_difference = False
    for order_item in order.items:
        received = ZERO
        received_amount = ZERO
        for item in receipt_items:
            if item.product_id != order_item.product_id:
                continue
            quantity = to_order_uom(db, order_item, item.accepted_quantity, item.uom_id)
            received += quantity
            received_amount += to_decimal(item.accepted_quantity) * to_decimal(
                item.unit_price
            )

        invoiced = ZERO
        invoiced_amount = ZERO
        for item in invoice_items:
            if item.product_id != order_item.product_id:
                continue
            quantity = to_order_uom(db, order_item, item.quantity, item.uom_id)
            invoiced += quantity
            invoiced_amount += to_decimal(item.quantity) * to_decimal(item.unit_price)

        invoice_unit_price = (
            money(invoiced_amount / invoiced) if invoiced > ZERO else None
        )
        quantity_difference = invoiced != received or received != to_decimal(
            order_item.quantity
        )
        price_difference = (
            invoice_unit_price is not None
            and money(invoice_unit_price) != money(order_item.unit_price)
        )
        if quantity_difference or price_difference:
            has_difference = True

        product = db.get(Product, order_item.product_id)
        rows.append({
            'product_id': order_item.product_id,
            'product_name': product.name if product else None,
            'uom_id': order_item.uom_id,
            'ordered_quantity': to_decimal(order_item.quantity),
            'received_quantity': received,
            'invoiced_quantity': invoiced,
            'order_unit_price': to_decimal(order_item.unit_price),
            'receipt_unit_price': (
                money(received_amount / received) if received > ZERO else None
            ),
            'invoice_unit_price': invoice_unit_price,
            'quantity_difference': quantity_difference,
            'price_difference': price_difference,
        })

    return {
        'purchase_order_id': order.id,
        'po_number': order.po_number,
        'status': order.status,
        'has_difference': has_difference,
        'rows': rows,
    }


def supplier_in_use(db: Session, supplier_id: int) -> bool:
    for model in (PurchaseOrder, PurchaseReceipt, PurchaseInvoice):
        if db.query(model.id).filter(model.supplier_id == supplier_id).first():
            return True
    return False


def ensure_warehouse(db: Session, warehouse_id: Optional[int]) -> Optional[int]:
    if warehouse_id is None:
        return None
    if db.get(Warehouse, warehouse_id) is None:
        raise HTTPException(status_code=404, detail=f'Warehouse {warehouse_id} bulunamadi')
    return warehouse_id
