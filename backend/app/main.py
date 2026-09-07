from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .auth import user_id_from_token
from .database import test_connection
from .models import DocumentImmutableError, LedgerImmutableError
from .services import audit_service
from .routers import (
    audit, auth, customers, invoices, naming_series, products, reports, sales,
    stock, transfers, users, warehouses,
)

app = FastAPI(
    title='ERP System',
    version='1.0.0',
    description='FastAPI + React + Supabase'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(customers.router)
app.include_router(products.router)
app.include_router(sales.router)
app.include_router(invoices.router)
app.include_router(reports.router)
app.include_router(reports.alerts_router)
app.include_router(warehouses.router)
app.include_router(stock.router)
app.include_router(transfers.router)
app.include_router(naming_series.router)
app.include_router(audit.router)


@app.middleware('http')
async def audit_context(request: Request, call_next):
    """Denetim izi icin istek baglamini kurar (kullanici get_current_user'da eklenir)."""
    client = request.headers.get('x-forwarded-for') or (
        request.client.host if request.client else None
    )
    audit_service.current_ip.set(client)
    # Kullanici token'dan cozulur: get_current_user senkron oldugu icin
    # threadpool'da kopyalanmis bir contextvar'a yazardi, buraya ulasmazdi.
    audit_service.current_user_id.set(
        user_id_from_token(request.headers.get('authorization'))
    )
    return await call_next(request)


@app.exception_handler(DocumentImmutableError)
def handle_document_immutable(request: Request, exc: DocumentImmutableError):
    """Onaylanmis/iptal belgeye yazma denemesi - 400 ile net mesaj don."""
    return JSONResponse(status_code=400, content={'detail': str(exc)})


@app.exception_handler(LedgerImmutableError)
def handle_ledger_immutable(request: Request, exc: LedgerImmutableError):
    return JSONResponse(status_code=400, content={'detail': str(exc)})


@app.exception_handler(SQLAlchemyError)
def handle_database_error(request: Request, exc: SQLAlchemyError):
    """Router'larda yakalanmayan veritabani hatalari icin son guvenlik agi."""
    return JSONResponse(
        status_code=500,
        content={'detail': f'Veritabani hatasi: {type(exc).__name__}'},
    )


@app.on_event('startup')
def startup_check():
    test_connection()
    print('Supabase baglantisi OK')


@app.get('/')
def read_root():
    return {'message': 'ERP API is running!', 'status': 'ok'}


@app.get('/health')
def health_check():
    return {'status': 'healthy'}
