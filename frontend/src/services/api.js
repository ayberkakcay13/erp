import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
});

/**
 * Backend HTTPException'lari {"detail": "..."} seklinde doner.
 * Pydantic validation hatalari (422) ise detail'i bir dizi olarak doner.
 * Her iki durumu da okunabilir tek bir mesaja cevirir.
 */
function toMessage(error) {
  if (error.response) {
    const detail = error.response.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : '';
          return field ? `${field}: ${d.msg}` : d.msg;
        })
        .join(', ');
    }
    if (error.response.status === 404) return 'Kayit bulunamadi';
    return `Sunucu hatasi (${error.response.status})`;
  }
  if (error.request) {
    return 'Backend\'e ulasilamiyor. Sunucu calisiyor mu? (http://localhost:8000)';
  }
  return error.message || 'Bilinmeyen bir hata olustu';
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const wrapped = new Error(toMessage(error));
    wrapped.status = error.response?.status;
    wrapped.original = error;
    return Promise.reject(wrapped);
  }
);

const unwrap = (promise) => promise.then((r) => r.data);

export const customerAPI = {
  getAll: (params) => unwrap(api.get('/api/customers', { params })),
  getById: (id) => unwrap(api.get(`/api/customers/${id}`)),
  create: (data) => unwrap(api.post('/api/customers', data)),
  update: (id, data) => unwrap(api.put(`/api/customers/${id}`, data)),
  delete: (id) => unwrap(api.delete(`/api/customers/${id}`)),
};

export const productAPI = {
  getAll: (params) => unwrap(api.get('/api/products', { params })),
  getById: (id) => unwrap(api.get(`/api/products/${id}`)),
  create: (data) => unwrap(api.post('/api/products', data)),
  update: (id, data) => unwrap(api.put(`/api/products/${id}`, data)),
  delete: (id) => unwrap(api.delete(`/api/products/${id}`)),
};

export const salesAPI = {
  getAll: (params) => unwrap(api.get('/api/sales', { params })),
  getById: (id) => unwrap(api.get(`/api/sales/${id}`)),
  create: (data) => unwrap(api.post('/api/sales', data)),
  updateStatus: (id, status) => unwrap(api.put(`/api/sales/${id}`, { status })),
};

export const invoiceAPI = {
  getAll: () => unwrap(api.get('/api/invoices')),
  getById: (id) => unwrap(api.get(`/api/invoices/${id}`)),
  // Fatura her zaman bir satistan uretilir: POST /api/sales/{sale_id}/invoice
  create: (saleId, data = {}) => unwrap(api.post(`/api/sales/${saleId}/invoice`, data)),
  updateStatus: (id, status) => unwrap(api.put(`/api/invoices/${id}`, { status })),
};

export default api;
