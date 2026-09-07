"""Tenant baglami ve PostgreSQL RLS koprusuu (Phase 12).

Izolasyon iki katmanli:
  1. **PostgreSQL Row Level Security** - asil guvenlik siniri. Uygulama
     `WHERE tenant_id = ?` yazmayi unutsa bile veritabani satiri dondurmez.
  2. Uygulama katmani - okunabilir hata mesajlari ve INSERT'lerde tenant_id
     doldurma. Guvenlik buna BIRAKILMAZ.

RLS politikalari `current_setting('app.current_tenant_id')` degerini okur.
Bu deger her TRANSACTION BASINDA yeniden yazilir (`after_begin` dinleyicisi):
`SET LOCAL` transaction sonunda temizlendigi icin, commit'ten sonra ayni
session'da acilan yeni transaction'da deger kaybolurdu.

Supabase Transaction Pooler (6543) baglantiyi transaction sonunda havuza
geri verir; `SET LOCAL` transaction'a bagli oldugu icin bir sonraki kiracinin
baglantisina sizmaz. Bu davranis test edilmistir
(tests/test_phase12_tenant.py::test_pooler_set_local_sizmiyor).

DIKKAT - `SET LOCAL ROLE`: Supabase'in `postgres` rolu **BYPASSRLS**
ayricaligiyla geliyor. Bu ayricalik RLS'i tamamen atlar; `ENABLE`/`FORCE ROW
LEVEL SECURITY` bile bir sey degistirmez. Bu yuzden her transaction, hicbir
ayricaligi olmayan `erp_app` roluyle calisir. Rol degisimi de transaction'a
bagli (`SET LOCAL`) oldugu icin havuz uzerinden sizmaz. Rolu migration
olusturur (migrate_phase12_tenant.py).
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from sqlalchemy import event, text
from sqlalchemy.orm import Session

# Istek basina tenant baglami
current_tenant_id: ContextVar[Optional[int]] = ContextVar('current_tenant_id', default=None)
# Platform sahibi (superadmin) ve bakim script'leri icin RLS muafiyeti
bypass_rls: ContextVar[bool] = ContextVar('bypass_rls', default=False)


@contextmanager
def tenant_scope(tenant_id: Optional[int], bypass: bool = False):
    """Belirli bir tenant baglaminda calistirir (script'ler ve testler icin)."""
    tenant_token = current_tenant_id.set(tenant_id)
    bypass_token = bypass_rls.set(bypass)
    try:
        yield
    finally:
        current_tenant_id.reset(tenant_token)
        bypass_rls.reset(bypass_token)


@contextmanager
def superuser_scope():
    """RLS muafiyetiyle calistirir. Giris akisi ve migration'lar icin.

    Giris sirasinda kullanici hangi tenant'a ait bilinmiyor; kullaniciyi
    bulabilmek icin tenant filtresi disinda tek bir okuma gerekiyor.
    """
    with tenant_scope(None, bypass=True):
        yield


# RLS'e tabi uygulama rolu. Migration bunu olusturur ve yetkilerini verir.
APP_DB_ROLE = 'erp_app'


def apply_to_connection(connection, tenant_id: Optional[int], bypass: bool) -> None:
    """Aktif transaction'a rol ve tenant ayarlarini yazar.

    `set_config(..., true)` = SET LOCAL: yalnizca bu transaction icin gecerli,
    commit/rollback'te otomatik temizlenir.
    """
    # Once role: `postgres` BYPASSRLS tasidigi icin politikalar ona islemez.
    connection.execute(text(f'SET LOCAL ROLE {APP_DB_ROLE}'))
    connection.execute(
        text("SELECT set_config('app.current_tenant_id', :value, true)"),
        {'value': '' if tenant_id is None else str(tenant_id)},
    )
    connection.execute(
        text("SELECT set_config('app.bypass_rls', :value, true)"),
        {'value': 'on' if bypass else 'off'},
    )


def _after_begin(session: Session, transaction, connection):  # noqa: ARG001
    apply_to_connection(connection, current_tenant_id.get(), bypass_rls.get())


def _stamp_tenant(session: Session, flush_context, instances):  # noqa: ARG001
    """Yeni kayitlara tenant_id'yi otomatik yazar.

    Her router'da elle set etmek yerine tek yerde: TenantMixin tasiyan her
    model bundan yararlanir. RLS'in WITH CHECK kurali da bunu bekler - yanlis
    ya da bos tenant_id ile INSERT veritabani tarafindan reddedilir.
    """
    tenant_id = current_tenant_id.get()
    if tenant_id is None:
        return
    for obj in session.new:
        table = getattr(obj, '__table__', None)
        if table is not None and 'tenant_id' in table.c:
            if getattr(obj, 'tenant_id', None) is None:
                obj.tenant_id = tenant_id


def register(session_factory) -> None:
    """Tenant baglamini her transaction basinda veritabanina yazar."""
    event.listen(session_factory, 'after_begin', _after_begin)
    event.listen(session_factory, 'before_flush', _stamp_tenant)
