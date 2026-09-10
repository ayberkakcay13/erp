"""Sales endpointleri - Phase 15 UYUM KATMANI.

`/api/sales` artik kaputun altinda SalesOrder + otomatik DeliveryNote
acar; eski davranisi (onay = stok dususu) korumak icin sale onaylanir
onaylanmaz TUM kalemleri kapsayan bir sevkiyat da acilip onaylanir. Yanit
sekli DEGISMEZ - Phase 10-14 testleri ve mevcut frontend bu router'a hic
dokunmadan calismaya devam eder.

Yeni gelistirme icin `routers/quotations.py`, `routers/sales_orders.py` ve
`routers/delivery_notes.py` kullanilmali; bu dosya yalniz geriye uyum icindir.

Stok hareketi zinciri (Phase 15):
  SalesOrder onayi -> stok hareketi YOK (niyet beyani)
  DeliveryNote onayi -> stok hareketi (reason='satis', ref_type='delivery')
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import Customer, DeliveryNote, DeliveryNoteItem, DocStatus, Product, Sale, SalesItem, User
from ..schemas import CancelRequest, SaleCreate, SaleResponse, SaleStatusUpdate
from ..services import credit_service, document_service, stock_service, uom_service
from ..services.tenant_service import require_module

router = APIRouter(
    prefix='/api/sales',
    tags=['sales'],
    dependencies=[Depends(get_current_user), Depends(require_module('sales'))],
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
            joinedload(Sale.items).joinedload(SalesItem.uom),
        )
        .filter(Sale.id == sale_id)
        .first()
    )
    if sale is None:
        raise HTTPException(status_code=404, detail=f'Sale {sale_id} bulunamadi')
    return sale


def _serialize(sale: Sale, credit_warning: dict | None = None) -> dict:
    """Detayli response: musteri bilgisi + tum item'lar + urun isimleri."""
    return {
        'id': sale.id,
        'customer_id': sale.customer_id,
        'sale_date': sale.sale_date,
        'so_number': sale.so_number,
        'warehouse_id': sale.warehouse_id,
        'total_amount': sale.total_amount,
        'status': sale.status,
        'docstatus': sale.docstatus,
        'docstatus_label': DocStatus.LABELS.get(sale.docstatus),
        'submitted_at': sale.submitted_at,
        'submitted_by': sale.submitted_by,
        'cancelled_at': sale.cancelled_at,
        'cancelled_by': sale.cancelled_by,
        'cancel_reason': sale.cancel_reason,
        'created_at': sale.created_at,
        'customer': sale.customer,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'tax_rate': item.tax_rate,
                'total_price': item.total_price,
                'warehouse_id': item.warehouse_id,
                'uom_id': item.uom_id,
                'uom_code': item.uom.code if item.uom else None,
                'stock_quantity': item.stock_quantity,
                'delivered_quantity': item.delivered_quantity,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
            }
            for item in sale.items
        ],
        'credit_warning': credit_warning,
    }


def _stock_quantity(db: Session, item) -> Decimal:
    """Kalemin miktarini urunun STOK BIRIMINE cevirir.

    Phase 13 kurali: ledger'a yazilan miktar her zaman stock_uom cinsindendir.
    Kalem farkli birimde girildiyse (koli satis, adet stok) donusum burada olur.
    `stock_quantity` daha once hesaplanmissa (kayitli satis kalemi) o kullanilir.
    """
    stored = getattr(item, 'stock_quantity', None)
    if stored is not None:
        return stock_service.to_decimal(stored)

    quantity = stock_service.to_decimal(item.quantity)
    uom_id = getattr(item, 'uom_id', None)
    if uom_id is None:
        return quantity
    product = db.get(Product, item.product_id)
    if product is None:
        return quantity
    return uom_service.to_stock_uom(db, product, quantity, uom_id)


def _requested_by_product_warehouse(db: Session, items) -> dict:
    """Satis kalemlerini (urun, depo) kirilimda STOK BIRIMI cinsinden toplar.

    Ayni urun birden fazla satirda olabilir; stok kontrolu ve ledger hareketi
    toplam miktar uzerinden yapilir.
    """
    totals: dict[tuple[int, int], Decimal] = {}
    for item in items:
        wh_id = stock_service.resolve_warehouse_id(db, getattr(item, 'warehouse_id', None))
        key = (item.product_id, wh_id)
        totals[key] = totals.get(key, stock_service.ZERO) + _stock_quantity(db, item)
    return totals


def _build_and_submit_delivery_note(db: Session, sale: Sale, user_id) -> DeliveryNote:
    """Uyum katmani: sale onaylanirken TUM kalemleri kapsayan bir sevkiyat acar.

    Stok hareketi burada, DeliveryNote onayinda olusur (Phase 15 kurali).
    Eski davranis (Sale onayinda aninda stok dususu) disaridan ayni gorunur.
    """
    delivery_note = DeliveryNote(
        sales_order_id=sale.id,
        customer_id=sale.customer_id,
        warehouse_id=sale.warehouse_id,
        delivery_date=sale.sale_date or date.today(),
        note='Otomatik sevkiyat (uyum katmani /api/sales)',
        created_by=user_id,
    )
    for item in sale.items:
        delivery_note.items.append(
            DeliveryNoteItem(
                sales_order_item_id=item.id,
                product_id=item.product_id,
                uom_id=item.uom_id,
                warehouse_id=item.warehouse_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                stock_quantity=item.stock_quantity,
            )
        )
    db.add(delivery_note)
    db.flush()
    document_service.submit(db, delivery_note, user_id=user_id)
    return delivery_note


def _cancel_linked_delivery_notes(db: Session, sale: Sale, user_id) -> None:
    """Sale iptal edilmeden once, onu sevk eden tum irsaliyeleri iptal eder."""
    notes = (
        db.query(DeliveryNote)
        .filter(
            DeliveryNote.sales_order_id == sale.id,
            DeliveryNote.docstatus == DocStatus.SUBMITTED,
        )
        .all()
    )
    for note in notes:
        document_service.cancel(
            db, note, user_id=user_id, reason='Bagli satis iptal edildi'
        )


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

    # Stok kontrolu: yetersizse hicbir kayit olusmadan 400 don.
    # Taslak satis stok tutmaz; kontrol onay aninda tekrar yapilir.
    for (product_id, wh_id), quantity in ({} if payload.save_as_draft else requested).items():
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
        warehouse_id=payload.warehouse_id,
        total_amount=stock_service.ZERO,
        status='pending',
    )

    total = stock_service.ZERO
    for item in payload.items:
        qty = stock_service.to_decimal(item.quantity)
        unit_price = stock_service.to_decimal(item.unit_price)
        # Fiyat girilen birim uzerinden; miktar ise stok birimine cevrilerek saklanir
        line_total = _money(qty * unit_price)
        total += line_total
        product = db.get(Product, item.product_id)
        sale.items.append(
            SalesItem(
                product_id=item.product_id,
                quantity=qty,
                unit_price=unit_price,
                tax_rate=item.tax_rate,
                total_price=line_total,
                warehouse_id=stock_service.resolve_warehouse_id(db, item.warehouse_id),
                uom_id=item.uom_id or product.sales_uom_id or product.stock_uom_id,
                stock_quantity=uom_service.to_stock_uom(db, product, qty, item.uom_id),
            )
        )
    sale.total_amount = _money(total)

    db.add(sale)
    db.flush()  # sale.id ledger ref_id olarak lazim

    credit_warning = None
    # Phase 11: belge onayi artik document_service uzerinden olusur.
    # Varsayilan davranis "olustur ve onayla" - save_as_draft=true ile taslak kalir.
    if not payload.save_as_draft:
        check = credit_service.check_credit(
            db, sale.customer_id, sale.total_amount,
            block_if_exceeded=payload.block_if_credit_exceeded,
        )
        if not check['allowed']:
            credit_warning = check
        document_service.submit(db, sale, user_id=current_user.id)
        # Phase 15: stok hareketi SalesOrder degil, DeliveryNote onayinda olusur.
        _build_and_submit_delivery_note(db, sale, current_user.id)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Satis kaydedilemedi: {exc}')

    return _serialize(_load_sale(db, sale.id), credit_warning)


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
        joinedload(Sale.items).joinedload(SalesItem.uom),
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
    sale_id: int,
    payload: SaleStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Satisin IS durumunu gunceller (pending / completed / cancelled).

    Phase 11 ile birlikte `status` ve `docstatus` ayri kavramlar:
    - `status` is akisi (beklemede / tamamlandi)
    - `docstatus` belge yasam dongusu (taslak / onayli / iptal)

    "cancelled" gonderilmesi belgeyi iptal eder; iptal `document_service`
    uzerinden gecer ve bagli sevkiyat(lar) once iptal edilerek stok geri
    alinir. Iptal edilmis bir belge TEKRAR ONAYLANAMAZ - duzeltme icin yeni
    satis olusturulur. (Bu kural Phase 4/10'daki "iptali geri al"
    davranisinin yerini alir.)
    """
    sale = _load_sale(db, sale_id)
    new_status = payload.status

    if new_status == 'cancelled':
        if sale.docstatus == DocStatus.CANCELLED:
            return _serialize(sale)  # zaten iptal - idempotent
        if sale.docstatus == DocStatus.DRAFT:
            raise HTTPException(
                status_code=400,
                detail='Taslak satis iptal edilemez, silinebilir',
            )
        _cancel_linked_delivery_notes(db, sale, current_user.id)
        document_service.cancel(db, sale, user_id=current_user.id)
        sale.status = 'cancelled'
    else:
        if sale.docstatus == DocStatus.CANCELLED:
            raise HTTPException(
                status_code=400,
                detail=(
                    'Iptal edilmis satis tekrar acilamaz. '
                    'Duzeltme icin yeni bir satis olusturun.'
                ),
            )
        sale.status = new_status

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Durum guncellenemedi: {exc}')
    return _serialize(_load_sale(db, sale_id))


@router.post('/{sale_id}/submit', response_model=SaleResponse)
def submit_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Taslak satisi onaylar: stok hareketi bu anda (sevkiyat uzerinden) olusur."""
    sale = _load_sale(db, sale_id)
    check = credit_service.check_credit(db, sale.customer_id, sale.total_amount)
    document_service.submit(db, sale, user_id=current_user.id)
    _build_and_submit_delivery_note(db, sale, current_user.id)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Satis onaylanamadi: {exc}')
    return _serialize(_load_sale(db, sale_id), None if check['allowed'] else check)


@router.post('/{sale_id}/cancel', response_model=SaleResponse)
def cancel_sale(
    sale_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Onayli satisi iptal eder: bagli sevkiyat(lar) iptal edilir, stok geri doner."""
    sale = _load_sale(db, sale_id)
    reason = payload.reason if payload else None
    _cancel_linked_delivery_notes(db, sale, current_user.id)
    document_service.cancel(db, sale, user_id=current_user.id, reason=reason)
    sale.status = 'cancelled'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Satis iptal edilemedi: {exc}')
    return _serialize(_load_sale(db, sale_id))


@router.delete('/{sale_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Yalnizca TASLAK satis silinebilir; onayli/iptal belge silinmez."""
    sale = _load_sale(db, sale_id)
    document_service.ensure_deletable(sale)
    try:
        db.delete(sale)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Satis silinemedi: {exc}')
    return None
