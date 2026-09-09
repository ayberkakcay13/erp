import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import AlertsPanel from '../components/AlertsPanel';
import DashboardCharts from '../components/DashboardCharts';
import {
  Badge,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  formatMoney,
} from '../components/ui';
import {
  customerAPI,
  invoiceAPI,
  productAPI,
  reportAPI,
  salesAPI,
} from '../services/api';
import { statusLabel, statusTone } from './Sales';

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
        recentSales: [...sales].sort((a, b) => b.id - a.id).slice(0, 5),
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

      {/* Phase 6: ciro ozeti + aylik trend + en cok satan urunler */}
      <DashboardCharts />

      <h3 className="text-sm font-medium text-gray-700 mb-2">Son Satislar</h3>
      {data.recentSales.length === 0 ? (
        <div className="text-sm text-gray-500">Henuz satis yok.</div>
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="recent-sales">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">No</th>
                <th className="text-left px-4 py-2 font-medium">Musteri</th>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-right px-4 py-2 font-medium">Tutar</th>
                <th className="text-left px-4 py-2 font-medium">Durum</th>
              </tr>
            </thead>
            <tbody>
              {data.recentSales.map((s) => (
                <tr key={s.id} className="border-t border-gray-100">
                  <td className="px-4 py-2">
                    <Link to={`/sales/${s.id}`} className="text-indigo-600 hover:underline">
                      #{s.id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-gray-800">{s.customer?.name ?? '-'}</td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(s.sale_date)}</td>
                  <td className="px-4 py-2 text-right font-medium">{formatMoney(s.total_amount)}</td>
                  <td className="px-4 py-2">
                    <Badge tone={statusTone[s.status] ?? 'gray'}>
                      {statusLabel[s.status] ?? s.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
