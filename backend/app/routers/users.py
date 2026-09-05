"""Kullanici yonetimi endpointleri. Hepsi sadece admin icindir."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import User
from ..schemas import UserResponse

router = APIRouter(prefix='/api/users', tags=['users'])


@router.get('', response_model=list[UserResponse])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.put('/{user_id}/deactivate', response_model=UserResponse)
def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Hesabi devre disi birakir. Admin kendi hesabini kapatamaz."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail='Kendi hesabini devre disi birakamazsin')

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f'Kullanici {user_id} bulunamadi')

    user.is_active = False
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Guncellenemedi: {exc}')
    db.refresh(user)
    return user


@router.put('/{user_id}/activate', response_model=UserResponse)
def activate_user(
    user_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f'Kullanici {user_id} bulunamadi')

    user.is_active = True
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Guncellenemedi: {exc}')
    db.refresh(user)
    return user
