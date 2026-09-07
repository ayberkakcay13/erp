"""Depolar arasi stok transferi (Phase 10).

Transfer onaylandiginda ledger'a IKI satir yazilir: cikis deposuna negatif
(`transfer_cikis`), giris deposuna pozitif (`transfer_giris`). Toplam stok
degismez - korunum kurali testle dogrulanir.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import DocStatus, Product, StockTransfer, StockTransferItem, User
from ..schemas import CancelRequest, StockTransferCreate, StockTransferResponse
from ..services import document_service, stock_service

router = APIRouter(
    prefix='/api/transfers',
    tags=['transfers'],
    dependencies=[Depends(get_current_user)],
)


def _load(db: Session, transfer_id: int) -> StockTransfer:
    transfer = (
        db.query(StockTransfer)
        .options(
            joinedload(StockTransfer.items).joinedload(StockTransferItem.product),
            joinedload(StockTransfer.from_warehouse),
            joinedload(StockTransfer.to_warehouse),
        )
        .filter(StockTransfer.id == transfer_id)
        .first()
    )
    if transfer is None:
        raise HTTPException(status_code=404, detail=f'Transfer {transfer_id} bulunamadi')
    return transfer


def _serialize(transfer: StockTransfer) -> dict:
    return {
        'id': transfer.id,
        'transfer_no': transfer.transfer_no,
        'from_warehouse_id': transfer.from_warehouse_id,
        'to_warehouse_id': transfer.to_warehouse_id,
        'transfer_date': transfer.transfer_date,
        'status': transfer.status,
        'docstatus': transfer.docstatus,
        'docstatus_label': DocStatus.LABELS.get(transfer.docstatus),
        'cancel_reason': transfer.cancel_reason,
        'note': transfer.note,
        'created_by': transfer.created_by,
        'created_at': transfer.created_at,
        'from_warehouse_name': (
            transfer.from_warehouse.name if transfer.from_warehouse else None
        ),
        'to_warehouse_name': transfer.to_warehouse.name if transfer.to_warehouse else None,
        'items': [
            {
                'id': item.id,
                'product_id': item.product_id,
                'quantity': item.quantity,
                'product_name': item.product.name if item.product else None,
                'product_sku': item.product.sku if item.product else None,
            }
            for item in transfer.items
        ],
    }


@router.post('', response_model=StockTransferResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(
    payload: StockTransferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transferi olusturur ve ayni transaction'da onaylayip ledger'a isler."""
    if payload.from_warehouse_id == payload.to_warehouse_id:
        raise HTTPException(status_code=400, detail='Cikis ve giris deposu ayni olamaz')

    from_id = stock_service.resolve_warehouse_id(db, payload.from_warehouse_id)
    to_id = stock_service.resolve_warehouse_id(db, payload.to_warehouse_id)

    # Ayni urun birden fazla satirda olabilir; toplam uzerinden kontrol et
    totals: dict[int, object] = {}
    for item in payload.items:
        product = db.get(Product, item.product_id)
        if product is None:
            raise HTTPException(
                status_code=404, detail=f'Product {item.product_id} bulunamadi'
            )
        qty = stock_service.to_decimal(item.quantity)
        totals[item.product_id] = totals.get(item.product_id, stock_service.ZERO) + qty

    for product_id, qty in totals.items():
        if not stock_service.check_availability(db, product_id, from_id, qty):
            product = db.get(Product, product_id)
            available = stock_service.get_stock(db, product_id, from_id)
            raise HTTPException(
                status_code=400,
                detail=(
                    f'"{product.name}" icin cikis deposunda stok yetersiz: '
                    f'{qty} istendi, {available} var'
                ),
            )

    # Phase 11: numara ve stok hareketi ONAY aninda, document_service uzerinden
    transfer = StockTransfer(
        transfer_no=None,
        from_warehouse_id=from_id,
        to_warehouse_id=to_id,
        transfer_date=payload.transfer_date or date.today(),
        status='draft',
        note=payload.note,
        created_by=current_user.id,
    )
    for item in payload.items:
        transfer.items.append(
            StockTransferItem(
                product_id=item.product_id,
                quantity=stock_service.to_decimal(item.quantity),
            )
        )
    db.add(transfer)
    db.flush()  # transfer.id ledger ref_id olarak lazim

    if not payload.save_as_draft:
        document_service.submit(db, transfer, user_id=current_user.id)
        transfer.status = 'completed'

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Transfer kaydedilemedi: {exc}')
    return _serialize(_load(db, transfer.id))


@router.get('', response_model=list[StockTransferResponse])
def list_transfers(
    warehouse_id: int | None = Query(None, description='Cikis ya da giris deposu'),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(StockTransfer).options(
        joinedload(StockTransfer.items).joinedload(StockTransferItem.product),
        joinedload(StockTransfer.from_warehouse),
        joinedload(StockTransfer.to_warehouse),
    )
    if warehouse_id is not None:
        query = query.filter(
            (StockTransfer.from_warehouse_id == warehouse_id)
            | (StockTransfer.to_warehouse_id == warehouse_id)
        )
    transfers = query.order_by(StockTransfer.id.desc()).offset(skip).limit(limit).all()
    return [_serialize(t) for t in transfers]


@router.get('/{transfer_id}', response_model=StockTransferResponse)
def get_transfer(transfer_id: int, db: Session = Depends(get_db)):
    return _serialize(_load(db, transfer_id))


@router.post('/{transfer_id}/submit', response_model=StockTransferResponse)
def submit_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Taslak transferi onaylar: numara atanir, iki ledger satiri olusur."""
    transfer = _load(db, transfer_id)
    document_service.submit(db, transfer, user_id=current_user.id)
    transfer.status = 'completed'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Transfer onaylanamadi: {exc}')
    return _serialize(_load(db, transfer_id))


@router.post('/{transfer_id}/cancel', response_model=StockTransferResponse)
def cancel_transfer(
    transfer_id: int,
    payload: CancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Onayli transferi iptal eder: hareketler ters kayitla geri alinir."""
    transfer = _load(db, transfer_id)
    document_service.cancel(
        db, transfer, user_id=current_user.id,
        reason=payload.reason if payload else None,
    )
    transfer.status = 'cancelled'
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Transfer iptal edilemedi: {exc}')
    return _serialize(_load(db, transfer_id))
