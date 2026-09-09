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
  // Phase 13: barkod, varyant
  byBarcode: (barcode) =>
    unwrap(api.get(`/api/products/by-barcode/${encodeURIComponent(barcode)}`)),
  variants: (id) => unwrap(api.get(`/api/products/${id}/variants`)),
  generateVariants: (id, data) =>
    unwrap(api.post(`/api/products/${id}/generate-variants`, data)),
  addBarcode: (id, data) => unwrap(api.post(`/api/products/${id}/barcodes`, data)),
  deleteBarcode: (id, barcodeId) =>
    unwrap(api.delete(`/api/products/${id}/barcodes/${barcodeId}`)),
};

// ---------------- Phase 13: urun yapisi ----------------

export const uomAPI = {
  getAll: (params) => unwrap(api.get('/api/uoms', { params })),
  create: (data) => unwrap(api.post('/api/uoms', data)),
  update: (id, data) => unwrap(api.put(`/api/uoms/${id}`, data)),
  delete: (id) => unwrap(api.delete(`/api/uoms/${id}`)),
  ensureDefaults: () => unwrap(api.post('/api/uoms/ensure-defaults')),
};

export const conversionAPI = {
  getAll: (params) => unwrap(api.get('/api/uom-conversions', { params })),
  create: (data) => unwrap(api.post('/api/uom-conversions', data)),
  delete: (id) => unwrap(api.delete(`/api/uom-conversions/${id}`)),
  preview: (params) => unwrap(api.get('/api/uom-conversions/convert', { params })),
};

export const itemGroupAPI = {
  getAll: () => unwrap(api.get('/api/item-groups')),
  tree: () => unwrap(api.get('/api/item-groups/tree')),
  create: (data) => unwrap(api.post('/api/item-groups', data)),
  update: (id, data) => unwrap(api.put(`/api/item-groups/${id}`, data)),
  delete: (id) => unwrap(api.delete(`/api/item-groups/${id}`)),
};

export const brandAPI = {
  getAll: () => unwrap(api.get('/api/brands')),
  create: (data) => unwrap(api.post('/api/brands', data)),
  update: (id, data) => unwrap(api.put(`/api/brands/${id}`, data)),
  delete: (id) => unwrap(api.delete(`/api/brands/${id}`)),
};

export const attributeAPI = {
  getAll: () => unwrap(api.get('/api/item-attributes')),
  create: (data) => unwrap(api.post('/api/item-attributes', data)),
  addValue: (id, data) => unwrap(api.post(`/api/item-attributes/${id}/values`, data)),
  delete: (id) => unwrap(api.delete(`/api/item-attributes/${id}`)),
};

export const salesAPI = {
  getAll: (params) => unwrap(api.get('/api/sales', { params })),
  getById: (id) => unwrap(api.get(`/api/sales/${id}`)),
  create: (data) => unwrap(api.post('/api/sales', data)),
  updateStatus: (id, status) => unwrap(api.put(`/api/sales/${id}`, { status })),
  // Phase 11: belge yasam dongusu
  submit: (id) => unwrap(api.post(`/api/sales/${id}/submit`)),
  cancel: (id, reason) => unwrap(api.post(`/api/sales/${id}/cancel`, { reason })),
  remove: (id) => unwrap(api.delete(`/api/sales/${id}`)),
};

export const invoiceAPI = {
  getAll: () => unwrap(api.get('/api/invoices')),
  getById: (id) => unwrap(api.get(`/api/invoices/${id}`)),
  // Fatura her zaman bir satistan uretilir: POST /api/sales/{sale_id}/invoice
  create: (saleId, data = {}) => unwrap(api.post(`/api/sales/${saleId}/invoice`, data)),
  updateStatus: (id, status) => unwrap(api.put(`/api/invoices/${id}`, { status })),
  // Phase 11: taslak fatura numara almaz; numara onayda atanir
  submit: (id) => unwrap(api.post(`/api/invoices/${id}/submit`)),
  cancel: (id, reason) => unwrap(api.post(`/api/invoices/${id}/cancel`, { reason })),
  remove: (id) => unwrap(api.delete(`/api/invoices/${id}`)),
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

// ---------------- Phase 10: Depo ve stok defteri ----------------

export const warehouseAPI = {
  getAll: (params) => unwrap(api.get('/api/warehouses', { params })),
  getById: (id) => unwrap(api.get(`/api/warehouses/${id}`)),
  create: (data) => unwrap(api.post('/api/warehouses', data)),
  update: (id, data) => unwrap(api.put(`/api/warehouses/${id}`, data)),
  delete: (id) => unwrap(api.delete(`/api/warehouses/${id}`)),
  stock: (id) => unwrap(api.get(`/api/warehouses/${id}/stock`)),
};

export const stockAPI = {
  balance: (params) => unwrap(api.get('/api/stock/balance', { params })),
  ledger: (params) => unwrap(api.get('/api/stock/ledger', { params })),
  productHistory: (id, params) =>
    unwrap(api.get(`/api/stock/product/${id}/history`, { params })),
  adjust: (data) => unwrap(api.post('/api/stock/adjustments', data)),
};

export const transferAPI = {
  getAll: (params) => unwrap(api.get('/api/transfers', { params })),
  getById: (id) => unwrap(api.get(`/api/transfers/${id}`)),
  create: (data) => unwrap(api.post('/api/transfers', data)),
  submit: (id) => unwrap(api.post(`/api/transfers/${id}/submit`)),
  cancel: (id, reason) => unwrap(api.post(`/api/transfers/${id}/cancel`, { reason })),
};

// ---------------- Phase 11: denetim izi ve numaralandirma ----------------

export const auditAPI = {
  list: (params) => unwrap(api.get('/api/audit-log', { params })),
  tables: () => unwrap(api.get('/api/audit-log/tables')),
  recordHistory: (table, recordId) =>
    unwrap(api.get(`/api/audit-log/${table}/${recordId}`)),
};

export const namingSeriesAPI = {
  getAll: (params) => unwrap(api.get('/api/naming-series', { params })),
  currentYear: () => unwrap(api.get('/api/naming-series/current-year')),
  update: (id, data) => unwrap(api.put(`/api/naming-series/${id}`, data)),
};

// ---------------- Phase 12: cok kiracili mimari ----------------

export const tenantAPI = {
  // Kullanicinin kendi firmasi
  me: () => unwrap(api.get('/api/tenant')),
  myModules: () => unwrap(api.get('/api/tenant/modules')),
  // Platform sahibi (superadmin)
  getAll: () => unwrap(api.get('/api/tenants')),
  getById: (id) => unwrap(api.get(`/api/tenants/${id}`)),
  create: (data) => unwrap(api.post('/api/tenants', data)),
  update: (id, data) => unwrap(api.put(`/api/tenants/${id}`, data)),
  setModules: (id, modules) => unwrap(api.put(`/api/tenants/${id}/modules`, { modules })),
};

export const userAPI = {
  getAll: () => unwrap(api.get('/api/users')),
  create: (data) => unwrap(api.post('/api/auth/register', data)),
  deactivate: (id) => unwrap(api.put(`/api/users/${id}/deactivate`)),
  activate: (id) => unwrap(api.put(`/api/users/${id}/activate`)),
};

export default api;
