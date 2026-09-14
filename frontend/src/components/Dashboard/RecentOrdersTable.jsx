import { useCallback, useEffect, useState } from 'react';
import { salesAPI } from '../../services/api';
import { formatDate } from './utils/dateUtils';
import { Badge, EmptyState, ErrorMessage, Loading, formatMoney } from '../ui';

const STATUS_LABEL = { pending: 'Beklemede', processing: 'Hazirlaniyor', delivered: 'Teslim Edildi' };
const STATUS_TONE = { pending: 'yellow', processing: 'blue', delivered: 'green' };

export default function RecentOrdersTable() {
  const [orders, setOrders] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await salesAPI.recentOrders();
      setOrders(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div data-testid="recent-orders" className="bg-white border border-gray-200 rounded p-4 mb-6">
      <h3 className="text-sm font-medium text-gray-700 mb-3">&#128230; Musteri Siparisleri</h3>

      {loading ? (
        <Loading label="Siparisler yukleniyor..." />
      ) : error ? (
        <ErrorMessage message={error} onRetry={load} />
      ) : orders.length === 0 ? (
        <EmptyState message="Henuz siparis yok." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="recent-orders-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Siparis No</th>
                <th className="text-left px-4 py-2 font-medium">Musteri</th>
                <th className="text-left px-4 py-2 font-medium">Urun</th>
                <th className="text-left px-4 py-2 font-medium">Siparis Tarihi</th>
                <th className="text-left px-4 py-2 font-medium">Teslimat Tarihi</th>
                <th className="text-right px-4 py-2 font-medium">Tutar</th>
                <th className="text-left px-4 py-2 font-medium">Durum</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr
                  key={o.id}
                  data-testid={`order-row-${o.id}`}
                  className="border-t border-gray-100 odd:bg-white even:bg-gray-50"
                >
                  <td className="px-4 py-2 text-gray-800">{o.id}</td>
                  <td className="px-4 py-2 text-gray-800">{o.customer}</td>
                  <td className="px-4 py-2 text-gray-600">{o.product}</td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(o.order_date)}</td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(o.delivery_date)}</td>
                  <td className="px-4 py-2 text-right font-medium">{formatMoney(o.amount)}</td>
                  <td className="px-4 py-2">
                    <Badge tone={STATUS_TONE[o.status] ?? 'gray'}>
                      {STATUS_LABEL[o.status] ?? o.status}
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
