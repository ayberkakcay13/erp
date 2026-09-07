import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# backend/.env dosyasini, calisma dizininden bagimsiz olarak yukle
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL bulunamadi. backend/.env dosyasini kontrol et.')

if 'sslmode' not in DATABASE_URL:
    DATABASE_URL += '?sslmode=require'

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Phase 11: denetim izi + belge degismezligi dinleyicileri tum session'lara baglanir
def _register_audit_listeners() -> None:
    from .services import audit_service  # gec import: dairesel bagimliligi kirar

    audit_service.register(SessionLocal)


_register_audit_listeners()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection() -> bool:
    """Supabase baglantisini dogrular. Basarisizsa exception firlatir."""
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    return True
