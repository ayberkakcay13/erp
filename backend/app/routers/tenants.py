"""Tenant yonetimi (Phase 12).

Iki ayri erisim seviyesi var:
- `/api/tenants*`  : platform sahibi (superadmin) - tum firmalari yonetir
- `/api/tenant/*`  : giris yapmis kullanicinin KENDI firmasi
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_superadmin
from ..database import get_db
from ..models import MODULE_CODES, Tenant, TenantModule, User
from ..schemas import (
    TenantCreate,
    TenantModuleResponse,
    TenantModuleUpdate,
    TenantResponse,
    TenantUpdate,
)
from ..services import tenant_context, tenant_service

router = APIRouter(
    prefix='/api/tenants',
    tags=['tenants'],
    dependencies=[Depends(require_superadmin)],
)

# Kendi firmasini goren kullanici endpointleri
me_router = APIRouter(
    prefix='/api/tenant',
    tags=['tenant'],
    dependencies=[Depends(get_current_user)],
)


def _serialize(tenant: Tenant, modules=None) -> dict:
    return {
        'id': tenant.id,
        'name': tenant.name,
        'slug': tenant.slug,
        'tax_number': tenant.tax_number,
        'is_active': tenant.is_active,
        'plan': tenant.plan,
        'created_at': tenant.created_at,
        'modules': [
            {'module_code': m.module_code, 'is_enabled': m.is_enabled}
            for m in sorted(modules or tenant.modules, key=lambda m: m.module_code)
        ],
    }


def _get_or_404(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f'Tenant {tenant_id} bulunamadi')
    return tenant


# ---------------- Superadmin ----------------

@router.post('', response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    """Yeni firma acar: moduller, varsayilan depo, seriler ve admin kullanici."""
    tenant = tenant_service.provision_tenant(
        db,
        name=payload.name,
        slug=payload.slug,
        tax_number=payload.tax_number,
        plan=payload.plan,
        modules=payload.modules,
        admin_email=payload.admin_email,
        admin_password=payload.admin_password,
        admin_full_name=payload.admin_full_name,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f'"{payload.slug}" kisa adi ya da yonetici e-postasi zaten kayitli',
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Tenant olusturulamadi: {exc}')
    db.refresh(tenant)
    return _serialize(tenant)


@router.get('', response_model=list[TenantResponse])
def list_tenants(db: Session = Depends(get_db)):
    return [_serialize(t) for t in db.query(Tenant).order_by(Tenant.id).all()]


@router.get('/{tenant_id}', response_model=TenantResponse)
def get_tenant(tenant_id: int, db: Session = Depends(get_db)):
    return _serialize(_get_or_404(db, tenant_id))


@router.put('/{tenant_id}', response_model=TenantResponse)
def update_tenant(tenant_id: int, payload: TenantUpdate, db: Session = Depends(get_db)):
    tenant = _get_or_404(db, tenant_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Bu kisa ad baska bir firmada kayitli')
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Tenant guncellenemedi: {exc}')
    db.refresh(tenant)
    return _serialize(tenant)


@router.put('/{tenant_id}/modules', response_model=list[TenantModuleResponse])
def set_modules(
    tenant_id: int, payload: TenantModuleUpdate, db: Session = Depends(get_db)
):
    """Firma bazli modul ac/kapa."""
    _get_or_404(db, tenant_id)
    unknown = set(payload.modules) - set(MODULE_CODES)
    if unknown:
        raise HTTPException(
            status_code=400, detail=f'Tanimsiz modul: {", ".join(sorted(unknown))}'
        )

    existing = {
        m.module_code: m
        for m in db.query(TenantModule).filter(TenantModule.tenant_id == tenant_id).all()
    }
    for code in MODULE_CODES:
        should_enable = code in payload.modules
        if code in existing:
            existing[code].is_enabled = should_enable
        else:
            db.add(
                TenantModule(
                    tenant_id=tenant_id, module_code=code, is_enabled=should_enable
                )
            )
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Moduller guncellenemedi: {exc}')

    rows = (
        db.query(TenantModule)
        .filter(TenantModule.tenant_id == tenant_id)
        .order_by(TenantModule.module_code)
        .all()
    )
    return [
        {'module_code': m.module_code, 'is_enabled': m.is_enabled} for m in rows
    ]


# ---------------- Kullanicinin kendi firmasi ----------------

@me_router.get('', response_model=TenantResponse)
def my_tenant(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.tenant_id is None:
        raise HTTPException(status_code=404, detail='Hesabiniz bir firmaya bagli degil')
    return _serialize(_get_or_404(db, current_user.tenant_id))


@me_router.get('/modules')
def my_modules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Frontend menuyu bu listeye gore kurar; kapali modul gorunmez."""
    tenant_id = current_user.tenant_id
    if current_user.is_superadmin or tenant_id is None:
        # Superadmin ve tek firma modunda tum moduller acik sayilir
        enabled = set(MODULE_CODES)
    else:
        with tenant_context.tenant_scope(tenant_id):
            enabled = tenant_service.enabled_modules(db, tenant_id)
    return {
        'tenant_id': tenant_id,
        'enabled': sorted(enabled),
        'all': list(MODULE_CODES),
    }
