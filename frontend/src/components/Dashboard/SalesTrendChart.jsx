import { useCallback, useEffect, useState } from 'react';
import { salesAPI } from '../../services/api';
import { formatDate } from './utils/dateUtils';
import SalesChartWidget from '../Shared/SalesChartWidget';
import { Badge, ErrorMessage, Loading, formatMoney } from '../ui';

// Phase 19: gercek SalesOrder.status backend'de pending/processing/delivered
// uc-durumuna eslenir (cancelled siparisler zaten sorgudan haric tutulur) -
// RecentOrdersTable.jsx ile ayni vokabuler.
const STATUS_LABEL = { pending: 'Beklemede', processing: 'Hazirlaniyor', delivered: 'Teslim Edildi' };
const STATUS_TONE = { pending: 'yellow', processing: 'blue', delivered: 'green' };

const PER_PAGE = 5;

/** Date -> "yyyy-MM-dd", backend'e query param olarak gonderilir */
const isoDate = (date) => formatDate(date, 'yyyy-MM-dd');

export default function SalesTrendChart() {
  const [page, setPage] = useState(1);
  const [salesRows, setSalesRows] = useState(null);
  const [totalPages, setTotalPages] = useState(1);
  const [tableLoading, setTableLoading] = useState(true);
  const [tableError, setTableError] = useState('');

  const loadTable = useCallback(async () => {
    setTableLoading(true);
    setTableError('');
    try {
      const { rows, total_pages: tp } = await salesAPI.recent(page, PER_PAGE);
      setSalesRows(rows);
      setTotalPages(tp);
    } catch (err) {
      setTableError(err.message);
    } finally {
      setTableLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadTable();
  }, [loadTable]);

  // useCallback: SalesChartWidget'a her render'da yeni bir fonksiyon referansi
  // gecmemek icin - yoksa tablo sayfalamasi degisince grafik de gereksiz yeniden yuklenir.
  const fetchChartData = useCallback((range, date) => salesAPI.trend(range, isoDate(date)), []);

  return (
    <div data-testid="sales-trend" className="bg-white border border-gray-200 rounded p-4 mb-6">
      <h3 className="text-sm font-medium text-gray-700 mb-4">Satis Trendi</h3>

      <SalesChartWidget fetchData={fetchChartData} />

      <h4 className="text-sm font-medium text-gray-700 mt-6 mb-2">Son 10 Satis</h4>
      {tableLoading ? (
        <Loading label="Satislar yukleniyor..." />
      ) : tableError ? (
        <ErrorMessage message={tableError} onRetry={loadTable} />
      ) : (
        <>
          <div className="bg-white border border-gray-200 rounded overflow-x-auto">
            <table className="w-full text-sm" data-testid="recent-sales-table">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="text-left px-4 py-2 font-medium">No</th>
                  <th className="text-left px-4 py-2 font-medium">Musteri</th>
                  <th className="text-left px-4 py-2 font-medium">Urun</th>
                  <th className="text-left px-4 py-2 font-medium">Siparis Tarihi</th>
                  <th className="text-left px-4 py-2 font-medium">Teslimat Tarihi</th>
                  <th className="text-right px-4 py-2 font-medium">Tutar</th>
                  <th className="text-left px-4 py-2 font-medium">Durum</th>
                </tr>
              </thead>
              <tbody>
                {salesRows.map((s) => (
                  <tr key={s.id} className="border-t border-gray-100">
                    <td className="px-4 py-2 text-gray-800">{s.id}</td>
                    <td className="px-4 py-2 text-gray-800">{s.customer}</td>
                    <td className="px-4 py-2 text-gray-600">{s.product}</td>
                    <td className="px-4 py-2 text-gray-600">{formatDate(s.order_date)}</td>
                    <td className="px-4 py-2 text-gray-600">{formatDate(s.delivery_date)}</td>
                    <td className="px-4 py-2 text-right font-medium">{formatMoney(s.amount)}</td>
                    <td className="px-4 py-2">
                      <Badge tone={STATUS_TONE[s.status] ?? 'gray'}>
                        {STATUS_LABEL[s.status] ?? s.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-center gap-3 mt-3 text-sm">
            <button
              type="button"
              data-testid="page-prev"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-2 py-1 rounded text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              &#9664; Geri
            </button>
            <span className="text-gray-500" data-testid="page-label">
              Sayfa {page}/{totalPages}
            </span>
            <button
              type="button"
              data-testid="page-next"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-2 py-1 rounded text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Ileri &#9654;
            </button>
          </div>
        </>
      )}
    </div>
  );
}
