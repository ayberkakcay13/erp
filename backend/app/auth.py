"""Kimlik dogrulama yardimcilari: sifre hashleme, JWT uretimi ve FastAPI bagimliliklari."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY bulunamadi. backend/.env dosyasina ekle.')

ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60'))

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# auto_error=False: token yoksa kendi 401 mesajimizi Turkce verebilelim
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user: User) -> str:
    """Kullanici icin JWT uretir. Token icinde sifre BULUNMAZ."""
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user.id),
        'email': user.email,
        'role': user.role,
        # Phase 12: tenant baglami token'da tasinir; her istekte buradan okunur
        'tenant_id': user.tenant_id,
        'is_superadmin': bool(user.is_superadmin),
        'iat': now,
        'exp': now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={'WWW-Authenticate': 'Bearer'},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Authorization: Bearer <token> header'indan kullaniciyi cozer."""
    if credentials is None:
        raise _unauthorized('Giris yapmalisin (token gonderilmedi)')

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise _unauthorized('Oturum suresi doldu, tekrar giris yap')
    except jwt.InvalidTokenError:
        raise _unauthorized('Gecersiz token')

    user_id = payload.get('sub')
    if user_id is None:
        raise _unauthorized('Gecersiz token icerigi')

    user = db.get(User, int(user_id))
    if user is None:
        raise _unauthorized('Kullanici bulunamadi')
    if not user.is_active:
        raise HTTPException(status_code=403, detail='Bu hesap devre disi birakilmis')
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Sadece admin rolundeki kullanicilara izin verir."""
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Bu islem icin admin yetkisi gerekli',
        )
    return current_user


def claims_from_token(authorization: str | None) -> dict:
    """Authorization header'indaki JWT'yi cozer, dogrulanamazsa bos sozluk.

    Middleware icin var: veritabanina gitmeden, istek baglaminda
    (threadpool'a girmeden once) kullanici ve tenant bilgisini kurar.
    YETKILENDIRME KARARI BURADA VERILMEZ - o is get_current_user'in;
    burasi yalnizca denetim izi ve RLS baglamini hazirlar.
    """
    if not authorization or not authorization.lower().startswith('bearer '):
        return {}
    token = authorization.split(' ', 1)[1].strip()
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return {}


def user_id_from_token(authorization: str | None) -> int | None:
    """Token'daki kullanici id'si (denetim izi icin)."""
    try:
        return int(claims_from_token(authorization)['sub'])
    except (KeyError, TypeError, ValueError):
        return None


def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    """Platform sahibi (tenant'lar ustu) islemler icin.

    Tenant admini kendi firmasinin yoneticisidir; tenant OLUSTURMA,
    modul acma/kapama gibi platform islemleri superadmin'e aittir.
    """
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=403, detail='Bu islem icin platform yoneticisi olmalisin'
        )
    return current_user
