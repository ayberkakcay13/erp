import { BrowserRouter, Route, Routes } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import Customers from './pages/Customers';
import Dashboard from './pages/Dashboard';
import Invoices from './pages/Invoices';
import Products from './pages/Products';
import SaleDetail from './pages/SaleDetail';
import Sales from './pages/Sales';

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-50">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Navbar />
          <main className="flex-1 overflow-auto p-3 sm:p-6">
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/customers" element={<Customers />} />
                <Route path="/products" element={<Products />} />
                <Route path="/sales" element={<Sales />} />
                <Route path="/sales/:id" element={<SaleDetail />} />
                <Route path="/invoices" element={<Invoices />} />
                <Route
                  path="*"
                  element={
                    <div data-testid="page-notfound" className="text-gray-600">
                      Sayfa bulunamadi.
                    </div>
                  }
                />
              </Routes>
            </ErrorBoundary>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}
