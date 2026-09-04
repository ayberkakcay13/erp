from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title='ERP System',
    version='1.0.0',
    description='FastAPI + React + Supabase'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.get('/')
def read_root():
    return {'message': 'ERP API is running!', 'status': 'ok'}

@app.get('/health')
def health_check():
    return {'status': 'healthy'}
