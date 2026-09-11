import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useSalesTrend } from '../../hooks/useSalesTrend';
import { formatPeriodLabel, formatStepLabel } from '../Dashboard/utils/dateUtils';
import { EmptyState, ErrorMessage, Loading, formatMoney } from '../ui';

const RANGES = [
  { key: 'daily', label: 'Gunluk' },
  { key: 'weekly', label: 'Haftalik' },
  { key: 'monthly', label: 'Aylik' },
  { key: 'yearly', label: 'Yillik' },
];

/** Grafiklerde binlik ayraciyla kisa gosterim (orn: 12.5B) */
function shortMoney(value) {
  const n = Number(value ?? 0);
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}B`;
  return String(n);
}

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const sales = payload.find((p) => p.dataKey === 'sales');
  const count = payload.find((p) => p.dataKey === 'count');
  return (
    <div className="bg-white border border-gray-200 rounded shadow-sm px-3 py-2 text-xs">
      <div className="font-medium text-gray-800 mb-1">{label}</div>
      {sales && <div className="text-blue-700">Tutar: {formatMoney(sales.value)}</div>}
      {count && <div className="text-emerald-700">Satis: {count.value} adet</div>}
    </div>
  );
}

/**
 * Phase 17-19: 4 mod + tarih navigasyonlu satis trendi grafigi.
 * SalesTrendChart.jsx'ten cikarildi; Dashboard ve musteri/urun detay modal'lari ortak kullanir.
 * State yonetimi useSalesTrend hook'unda; fetchData(timeRange, date) verinin
 * nereden geldigini cagirana birakir (Dashboard/musteri/urun API'si).
 */
export default function SalesChartWidget({ fetchData }) {
  const {
    timeRange,
    setTimeRange,
    selectedDate,
    step,
    data: chartData,
    loading,
    error,
    reload,
  } = useSalesTrend(fetchData);

  const hasChartData = chartData?.some((d) => d.sales > 0 || d.count > 0);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div className="flex flex-wrap gap-2" data-testid="range-buttons">
          {RANGES.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              data-testid={`range-${key}`}
              onClick={() => setTimeRange(key)}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                timeRange === key
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-center gap-3 mb-4 text-sm">
        <button
          type="button"
          data-testid="period-prev"
          onClick={() => step(-1)}
          className="px-2 py-1 rounded text-gray-600 hover:bg-gray-100"
        >
          &#9664; {formatStepLabel(timeRange, selectedDate, -1)}
        </button>
        <span className="font-medium text-gray-800 min-w-[9rem] text-center" data-testid="period-label">
          {formatPeriodLabel(timeRange, selectedDate)}
        </span>
        <button
          type="button"
          data-testid="period-next"
          onClick={() => step(1)}
          className="px-2 py-1 rounded text-gray-600 hover:bg-gray-100"
        >
          {formatStepLabel(timeRange, selectedDate, 1)} &#9654;
        </button>
      </div>

      {loading ? (
        <Loading label="Grafik yukleniyor..." />
      ) : error ? (
        <ErrorMessage message={error} onRetry={reload} />
      ) : hasChartData ? (
        <div style={{ width: '100%', height: 300 }} data-testid="chart-sales-trend">
          <ResponsiveContainer>
            <ComposedChart data={chartData} margin={{ top: 5, right: 15, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <YAxis
                yAxisId="left"
                tickFormatter={shortMoney}
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                allowDecimals={false}
                tick={{ fontSize: 11 }}
                stroke="#94a3b8"
              />
              <Tooltip content={<TrendTooltip />} cursor={{ fill: '#f8fafc' }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="left" dataKey="sales" fill="#3b82f6" name="Tutar (TL)" radius={[4, 4, 0, 0]} />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="count"
                stroke="#10b981"
                strokeWidth={2}
                dot={{ r: 3, fill: '#10b981' }}
                activeDot={{ r: 5 }}
                name="Satis (adet)"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <EmptyState message="Bu donemde satis yok." />
      )}
    </div>
  );
}
