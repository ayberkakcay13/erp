import { BrowserRouter, Route, Routes } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import Navbar from './components/Navbar';
import ProtectedRoute from './components/ProtectedRoute';
import Sidebar from './components/Sidebar';
import { AlertsProvider } from './context/AlertsContext';
import { AuthProvider } from './context/AuthContext';
import AuditLog from './pages/AuditLog';
import Customers from './pages/Customers';
import Dashboard from './pages/Dashboard';
import Invoices from './pages/Invoices';
import Login from './pages/Login';
import Products from './pages/Products';
import SaleDetail from './pages/SaleDetail';
import Sales from './pages/Sales';
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
function Protected({ children, adminOnly = false }) {
  return (
    <ProtectedRoute adminOnly={adminOnly}>
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
          <Route path="/sales" element={<Protected><Sales /></Protected>} />
          <Route path="/sales/:id" element={<Protected><SaleDetail /></Protected>} />
          <Route path="/invoices" element={<Protected><Invoices /></Protected>} />
          <Route path="/stock" element={<Protected><StockBalance /></Protected>} />
          <Route path="/stock/ledger" element={<Protected><StockLedger /></Protected>} />
          <Route path="/transfers" element={<Protected><Transfers /></Protected>} />
          <Route path="/users" element={<Protected adminOnly><Users /></Protected>} />
          <Route
            path="/audit-log"
            element={<Protected adminOnly><AuditLog /></Protected>}
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
