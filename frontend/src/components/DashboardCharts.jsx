import { useCallback, useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { reportAPI } from '../services/api';
import { EmptyState, ErrorMessage, Loading, formatMoney } from './ui';

const BAR_COLORS = ['#4f46e5', '#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe'];

/** Grafiklerde binlik ayraciyla kisa gosterim (orn: 12.5B) */
function shortMoney(value) {
  const n = Number(value ?? 0);
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}B`;
  return String(n);
}

function ChartCard({ title, hint, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-gray-800">{title}</h3>
        {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

function ChartTooltip({ active, payload, label, valueLabel }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 rounded shadow-sm px-3 py-2 text-xs">
      <div className="font-medium text-gray-800 mb-1">{row.name ?? label}</div>
      <div className="text-indigo-700">
        {valueLabel}: {payload[0].dataKey === 'quantity'
          ? `${payload[0].value} adet`
          : formatMoney(payload[0].value)}
      </div>
      {row.count !== undefined && (
        <div className="text-gray-500">{row.count} satis</div>
      )}
      {row.revenue !== undefined && (
        <div className="text-gray-500">{formatMoney(row.revenue)} ciro</div>
      )}
    </div>
  );
}

export default function DashboardCharts() {
  const [monthly, setMonthly] = useState(null);
  const [top, setTop] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [m, t, r] = await Promise.all([
        reportAPI.salesByMonth(6),
        reportAPI.topProducts(5),
        reportAPI.revenueSummary(),
      ]);
      setMonthly(m);
      setTop(t);
      setRevenue(r);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <Loading label="Raporlar yukleniyor..." />;
  if (error) return <ErrorMessage message={error} onRetry={load} />;

  const hasMonthly = monthly?.some((m) => m.total > 0);
  const hasTop = top?.length > 0;

  const periods = [
    { key: 'today', label: 'Bugun' },
    { key: 'week', label: 'Bu Hafta' },
    { key: 'month', label: 'Bu Ay' },
    { key: 'year', label: 'Bu Yil' },
  ];

  return (
    <div data-testid="dashboard-charts">
      <h3 className="text-sm font-medium text-gray-700 mb-2">
        Ciro Ozeti
        <span className="text-xs text-gray-400 font-normal ml-2">
          (iptal edilen satislar haric)
        </span>
      </h3>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {periods.map(({ key, label }) => (
          <div key={key} className="bg-white border border-gray-200 rounded p-4">
            <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
            <div
              className="text-xl font-semibold text-gray-800 mt-1"
              data-testid={`revenue-${key}`}
            >
              {formatMoney(revenue[key].total)}
            </div>
            <div className="text-xs text-gray-500 mt-1" data-testid={`revenue-count-${key}`}>
              {revenue[key].count} satis
            </div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mb-6">
        <ChartCard title="Aylik Satis Trendi" hint="Son 6 ay, iptaller haric">
          {hasMonthly ? (
            <div style={{ width: '100%', height: 260 }} data-testid="chart-monthly">
              <ResponsiveContainer>
                <LineChart data={monthly} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                  <YAxis tickFormatter={shortMoney} tick={{ fontSize: 11 }} stroke="#94a3b8" />
                  <Tooltip content={<ChartTooltip valueLabel="Tutar" />} />
                  <Line
                    type="monotone"
                    dataKey="total"
                    stroke="#4f46e5"
                    strokeWidth={2}
                    dot={{ r: 3, fill: '#4f46e5' }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState message="Son 6 ayda satis yok. Satis ekledikce grafik dolacak." />
          )}
        </ChartCard>

        <ChartCard title="En Cok Satan 5 Urun" hint="Satilan adet bazinda">
          {hasTop ? (
            <div style={{ width: '100%', height: 260 }} data-testid="chart-top-products">
              <ResponsiveContainer>
                <BarChart
                  data={top}
                  layout="vertical"
                  margin={{ top: 5, right: 15, bottom: 5, left: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={110}
                    tick={{ fontSize: 11 }}
                    stroke="#94a3b8"
                  />
                  <Tooltip content={<ChartTooltip valueLabel="Miktar" />} cursor={{ fill: '#f8fafc' }} />
                  <Bar dataKey="quantity" radius={[0, 4, 4, 0]}>
                    {top.map((entry, i) => (
                      <Cell key={entry.product_id} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState message="Henuz satilan urun yok." />
          )}
        </ChartCard>
      </div>
    </div>
  );
}
