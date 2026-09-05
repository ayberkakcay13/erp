import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
});

// Token ve 401 davranisi AuthContext tarafindan buraya baglanir
let authToken = null;
let onUnauthorized = null;

export function setAuthToken(token) {
  authToken = token;
}

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

api.interceptors.request.use((config) => {
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`;
  }
  return config;
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
    const status = error.response?.status;
    // Token yok/gecersiz/suresi dolmus: oturumu kapat, login sayfasina dusulsun.
    // Login denemesinin kendi 401'i haric - orada "sifre hatali" mesaji gosterilmeli.
    const isLoginRequest = error.config?.url?.includes('/api/auth/login');
    if (status === 401 && !isLoginRequest && onUnauthorized) {
      onUnauthorized();
    }
    const wrapped = new Error(toMessage(error));
    wrapped.status = status;
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

export const authAPI = {
  login: (email, password) => unwrap(api.post('/api/auth/login', { email, password })),
  register: (data) => unwrap(api.post('/api/auth/register', data)),
  me: () => unwrap(api.get('/api/auth/me')),
};

/**
 * Fatura PDF'ini indirir.
 * Endpoint token istedigi icin duz bir <a href> ile indirilemiyor;
 * dosya blob olarak cekilip gecici bir link uzerinden kaydettiriliyor.
 */
export async function downloadInvoicePdf(invoiceId, invoiceNumber) {
  const response = await api.get(`/api/invoices/${invoiceId}/pdf`, {
    responseType: 'blob',
  });
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${invoiceNumber || `fatura-${invoiceId}`}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export const reportAPI = {
  salesByMonth: (months = 6) =>
    unwrap(api.get('/api/reports/sales-by-month', { params: { months } })),
  topProducts: (limit = 5) =>
    unwrap(api.get('/api/reports/top-products', { params: { limit } })),
  revenueSummary: () => unwrap(api.get('/api/reports/revenue-summary')),
  productHistory: (id) => unwrap(api.get(`/api/reports/product/${id}/history`)),
};

export const alertAPI = {
  lowStock: (threshold) =>
    unwrap(api.get('/api/alerts/low-stock', { params: threshold ? { threshold } : {} })),
  overdueInvoices: (days) =>
    unwrap(api.get('/api/alerts/overdue-invoices', { params: days ? { days } : {} })),
  summary: () => unwrap(api.get('/api/alerts/summary')),
};

export const userAPI = {
  getAll: () => unwrap(api.get('/api/users')),
  create: (data) => unwrap(api.post('/api/auth/register', data)),
  deactivate: (id) => unwrap(api.put(`/api/users/${id}/deactivate`)),
  activate: (id) => unwrap(api.put(`/api/users/${id}/activate`)),
};

export default api;
