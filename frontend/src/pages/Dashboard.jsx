import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import AlertsPanel from '../components/AlertsPanel';
import RecentOrdersTable from '../components/Dashboard/RecentOrdersTable';
import SalesTrendChart from '../components/Dashboard/SalesTrendChart';
import { ErrorMessage, Loading, PageHeader, formatMoney } from '../components/ui';
import {
  customerAPI,
  invoiceAPI,
  productAPI,
  reportAPI,
  salesAPI,
} from '../services/api';

function StatCard({ label, value, to, testid, hint }) {
  const card = (
    <div className="bg-white border border-gray-200 rounded p-4 h-full hover:border-indigo-300 transition-colors">
      <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
      <div className="text-2xl font-semibold text-gray-800 mt-1" data-testid={testid}>
        {value}
      </div>
      {hint && <div className="text-xs text-gray-500 mt-1">{hint}</div>}
    </div>
  );
  return to ? <Link to={to}>{card}</Link> : card;
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      // Ozet degerler mevcut list endpoint'lerinden hesaplaniyor, ayri bir backend
      // endpoint'ine gerek yok.
      const [customers, products, sales, invoices] = await Promise.all([
        customerAPI.getAll(),
        productAPI.getAll(),
        salesAPI.getAll(),
        invoiceAPI.getAll(),
      ]);
      // Satin alma modulu kapaliysa bu iki cagri 403 doner; kartlar gizlenir
      const [pendingOrders, purchaseMonths] = await Promise.all([
        reportAPI.pendingPurchaseOrders().catch(() => null),
        reportAPI.purchaseSummary(1).catch(() => null),
      ]);
      setData({
        pendingOrders: pendingOrders ? pendingOrders.length : null,
        overdueOrders: pendingOrders
          ? pendingOrders.filter((o) => o.is_overdue).length
          : 0,
        purchaseThisMonth: purchaseMonths
          ? Number(purchaseMonths[purchaseMonths.length - 1]?.total ?? 0)
          : null,
        customers: customers.length,
        products: products.length,
        sales: sales.length,
        invoices: invoices.length,
        revenue: sales.reduce((sum, s) => sum + Number(s.total_amount ?? 0), 0),
        lowStock: products.filter((p) => p.stock < 10).length,
        unpaidInvoices: invoices.filter((i) => i.status !== 'paid').length,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <Loading />;
  if (error) return <ErrorMessage message={error} onRetry={load} />;

  return (
    <div data-testid="page-Dashboard">
      <PageHeader title="Dashboard" />

      {/* Phase 9: dusuk stok ve gecikmis fatura uyarilari */}
      <AlertsPanel />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Musteri" value={data.customers} to="/customers" testid="stat-customers" />
        <StatCard
          label="Urun"
          value={data.products}
          to="/products"
          testid="stat-products"
          hint={data.lowStock > 0 ? `${data.lowStock} urunde stok az` : 'Stoklar yeterli'}
        />
        <StatCard label="Satis" value={data.sales} to="/sales" testid="stat-sales" />
        <StatCard
          label="Fatura"
          value={data.invoices}
          to="/invoices"
          testid="stat-invoices"
          hint={data.unpaidInvoices > 0 ? `${data.unpaidInvoices} tanesi odenmedi` : 'Hepsi odendi'}
        />
      </div>

      {data.pendingOrders !== null && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard
            label="Bekleyen Siparis"
            value={data.pendingOrders}
            to="/purchase/orders"
            testid="stat-pending-orders"
            hint={
              data.overdueOrders > 0
                ? `${data.overdueOrders} tanesi gecikmis`
                : 'Gecikme yok'
            }
          />
          <StatCard
            label="Bu Ay Alim Tutari"
            value={formatMoney(data.purchaseThisMonth ?? 0)}
            to="/purchase/receipts"
            testid="stat-purchase-month"
            hint="Onayli mal kabuller"
          />
        </div>
      )}

      <div className="bg-indigo-600 text-white rounded p-5 mb-6">
        <div className="text-xs uppercase tracking-wide text-indigo-200">Toplam Satis Tutari</div>
        <div className="text-3xl font-semibold mt-1" data-testid="stat-revenue">
          {formatMoney(data.revenue)}
        </div>
      </div>

      {/* Phase 16: satis trendi grafigi (4 mod + tarih nav) + son 10 satis tablosu (mock veri) */}
      <SalesTrendChart />

      {/* Phase 16: musteri siparisleri tablosu (mock veri) */}
      <RecentOrdersTable />
    </div>
  );
}
