import { BrowserRouter, Route, Routes } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import Navbar from './components/Navbar';
import ProtectedRoute from './components/ProtectedRoute';
import Sidebar from './components/Sidebar';
import { AlertsProvider } from './context/AlertsContext';
import { AuthProvider } from './context/AuthContext';
import AuditLog from './pages/AuditLog';
import Catalog from './pages/Catalog';
import Customers from './pages/Customers';
import Dashboard from './pages/Dashboard';
import Invoices from './pages/Invoices';
import Login from './pages/Login';
import Products from './pages/Products';
import PurchaseInvoices from './pages/PurchaseInvoices';
import PurchaseMatch from './pages/PurchaseMatch';
import PurchaseOrders from './pages/PurchaseOrders';
import PurchaseReceipts from './pages/PurchaseReceipts';
import SaleDetail from './pages/SaleDetail';
import Sales from './pages/Sales';
import Suppliers from './pages/Suppliers';
import Tenants from './pages/Tenants';
import StockBalance from './pages/StockBalance';
import StockLedger from './pages/StockLedger';
import Transfers from './pages/Transfers';
import Users from './pages/Users';

/** Giris yapmis kullanicinin gordugu menulu duzen. */
function AppLayout({ children }) {
  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Navbar />
        <main className="flex-1 overflow-auto p-3 sm:p-6">
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </div>
    </div>
  );
}

/** Korumali sayfalari tek yerde sarmalar. */
function Protected({ children, adminOnly = false, superadminOnly = false }) {
  return (
    <ProtectedRoute adminOnly={adminOnly} superadminOnly={superadminOnly}>
      <AppLayout>{children}</AppLayout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AlertsProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Protected><Dashboard /></Protected>} />
          <Route path="/customers" element={<Protected><Customers /></Protected>} />
          <Route path="/products" element={<Protected><Products /></Protected>} />
          <Route path="/catalog" element={<Protected adminOnly><Catalog /></Protected>} />
          <Route path="/sales" element={<Protected><Sales /></Protected>} />
          <Route path="/sales/:id" element={<Protected><SaleDetail /></Protected>} />
          <Route path="/invoices" element={<Protected><Invoices /></Protected>} />
          <Route path="/suppliers" element={<Protected><Suppliers /></Protected>} />
          <Route
            path="/purchase/orders"
            element={<Protected><PurchaseOrders /></Protected>}
          />
          <Route
            path="/purchase/receipts"
            element={<Protected><PurchaseReceipts /></Protected>}
          />
          <Route
            path="/purchase/invoices"
            element={<Protected><PurchaseInvoices /></Protected>}
          />
          <Route
            path="/purchase/match/:id"
            element={<Protected><PurchaseMatch /></Protected>}
          />
          <Route path="/stock" element={<Protected><StockBalance /></Protected>} />
          <Route path="/stock/ledger" element={<Protected><StockLedger /></Protected>} />
          <Route path="/transfers" element={<Protected><Transfers /></Protected>} />
          <Route path="/users" element={<Protected adminOnly><Users /></Protected>} />
          <Route
            path="/audit-log"
            element={<Protected adminOnly><AuditLog /></Protected>}
          />
          <Route
            path="/tenants"
            element={<Protected superadminOnly><Tenants /></Protected>}
          />
          <Route
            path="*"
            element={
              <Protected>
                <div data-testid="page-notfound" className="text-gray-600">
                  Sayfa bulunamadi.
                </div>
              </Protected>
            }
          />
        </Routes>
        </AlertsProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
