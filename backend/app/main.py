from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .database import test_connection
from .routers import customers, invoices, products, sales

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

app.include_router(customers.router)
app.include_router(products.router)
app.include_router(sales.router)
app.include_router(invoices.router)


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
