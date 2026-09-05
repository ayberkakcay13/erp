"""Kimlik dogrulama endpointleri: kayit, giris ve mevcut kullanici bilgisi."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import (create_access_token, get_current_user, hash_password,
                    require_admin, verify_password)
from ..database import get_db
from ..models import User
from ..schemas import Token, UserCreate, UserLogin, UserResponse

router = APIRouter(prefix='/api/auth', tags=['auth'])

optional_bearer = HTTPBearer(auto_error=False)


@router.post('/register', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
):
    """Yeni kullanici olusturur.

    Sistemde hic kullanici yoksa ilk kayit serbesttir ve otomatik admin olur
    (kurulum adimi). Sonraki kayitlar sadece admin token'i ile yapilabilir.
    """
    user_count = db.query(User).count()
    is_first_user = user_count == 0

    if is_first_user:
        role = 'admin'  # ilk kullanici her zaman admin, gonderilen rol yok sayilir
    else:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Yeni kullanici olusturmak icin admin olarak giris yapmalisin',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        # Token'i dogrula ve admin mi diye bak
        require_admin(get_current_user(credentials=credentials, db=db))
        role = payload.role

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=role,
        full_name=payload.full_name,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f'"{payload.email}" e-postasi zaten kayitli'
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Kullanici olusturulamadi: {exc}')
    db.refresh(user)
    return user


@router.post('/login', response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    # Kullanici yoksa da sifre yanlissa da ayni mesaj: hangi e-postanin
    # kayitli oldugu disari sizmasin
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='E-posta veya sifre hatali',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail='Bu hesap devre disi birakilmis')

    return Token(access_token=create_access_token(user), user=UserResponse.model_validate(user))


@router.get('/me', response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user
