"""Tenant kurulumu ve modul aktivasyonu (Phase 12)."""
from datetime import date
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    DEFAULT_ENABLED_MODULES,
    MODULE_CODES,
    Tenant,
    TenantModule,
    User,
    Warehouse,
)
from . import naming_service, tenant_context


def provision_tenant(
    db: Session,
    name: str,
    slug: str,
    tax_number: Optional[str] = None,
    plan: str = 'free',
    modules: Optional[list] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None,
    admin_full_name: Optional[str] = None,
) -> Tenant:
    """Yeni tenant'i calisir halde acar.

    Tek transaction: tenant + moduller + varsayilan admin + varsayilan depo +
    numaralandirma serileri. Yarim kurulmus bir firma olusmaz.
    commit ETMEZ - cagiran router commit eder.
    """
    from ..auth import hash_password  # gec import: dairesel bagimliligi kirar

    tenant = Tenant(
        name=name,
        slug=slug,
        tax_number=tax_number,
        plan=plan if plan in ('free', 'basic', 'pro') else 'free',
        is_active=True,
    )
    db.add(tenant)
    db.flush()  # tenant.id asagidaki tum kayitlar icin gerekli

    enabled = set(modules if modules is not None else DEFAULT_ENABLED_MODULES)
    unknown = enabled - set(MODULE_CODES)
    if unknown:
        raise HTTPException(
            status_code=400, detail=f'Tanimsiz modul: {", ".join(sorted(unknown))}'
        )
    for code in MODULE_CODES:
        db.add(
            TenantModule(
                tenant_id=tenant.id, module_code=code, is_enabled=code in enabled
            )
        )

    # Varsayilan depo: stok hareketi ilk gunden itibaren calissin
    db.add(
        Warehouse(
            tenant_id=tenant.id,
            code='MERKEZ',
            name='Merkez Depo',
            warehouse_type='merkez',
            is_active=True,
            is_default=True,
        )
    )

    # Numaralandirma serileri tenant bazli acilir
    year = date.today().year
    for doc_type in naming_service.DEFAULT_SERIES:
        naming_service.ensure_series(db, doc_type, year, tenant_id=tenant.id)

    if admin_email and admin_password:
        db.add(
            User(
                email=admin_email,
                hashed_password=hash_password(admin_password),
                role='admin',
                full_name=admin_full_name or name,
                is_active=True,
                tenant_id=tenant.id,
                is_superadmin=False,
            )
        )

    db.flush()
    return tenant


# ---------------- Modul aktivasyonu ----------------

def enabled_modules(db: Session, tenant_id: Optional[int]) -> set:
    """Tenant'in acik modul kodlari."""
    if tenant_id is None:
        return set(MODULE_CODES)  # superadmin / tenant'siz baglam
    rows = (
        db.query(TenantModule.module_code)
        .filter(TenantModule.tenant_id == tenant_id, TenantModule.is_enabled.is_(True))
        .all()
    )
    return {row[0] for row in rows}


def require_module(module_code: str):
    """Kapali modulun endpoint'ini 403 ile kapatan dependency.

    Kullanim:
        @router.get('', dependencies=[Depends(require_module('stock'))])
    """
    if module_code not in MODULE_CODES:
        raise ValueError(f'Tanimsiz modul kodu: {module_code}')

    def dependency(db: Session = Depends(get_db)) -> None:
        if tenant_context.bypass_rls.get():
            return  # superadmin modul kisitindan muaf
        tenant_id = tenant_context.current_tenant_id.get()
        if tenant_id is None:
            return  # tenant'siz kurulum (tek firma modu) - kisit uygulanmaz
        if module_code not in enabled_modules(db, tenant_id):
            raise HTTPException(
                status_code=403, detail='Bu modul hesabinizda aktif degil'
            )

    return dependency
