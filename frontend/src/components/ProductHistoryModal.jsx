import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { reportAPI } from '../services/api';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  formatDate,
  formatMoney,
} from './ui';

const statusTone = { pending: 'yellow', completed: 'green', cancelled: 'red' };
const statusLabel = { pending: 'Bekliyor', completed: 'Tamamlandi', cancelled: 'Iptal' };

export default function ProductHistoryModal({ productId, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    reportAPI
      .productHistory(productId)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [productId]);

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-10"
      onClick={onClose}
      data-testid="product-history-modal"
    >
      <div
        className="bg-white rounded shadow-lg max-w-2xl w-full max-h-[85vh] overflow-auto p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <ErrorMessage message={error} />
        {!data && !error ? (
          <Loading />
        ) : data ? (
          <>
            <h3 className="text-lg font-semibold text-gray-800">{data.product_name}</h3>
            <p className="font-mono text-xs text-gray-500 mb-4">{data.sku}</p>

            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="bg-gray-50 rounded p-3">
                <div className="text-xs text-gray-500">Mevcut Stok</div>
                <div className="text-lg font-semibold text-gray-800" data-testid="history-stock">
                  {data.current_stock}
                </div>
              </div>
              <div className="bg-gray-50 rounded p-3">
                <div className="text-xs text-gray-500">Toplam Satilan</div>
                <div className="text-lg font-semibold text-gray-800" data-testid="history-sold">
                  {data.total_sold}
                </div>
              </div>
              <div className="bg-gray-50 rounded p-3">
                <div className="text-xs text-gray-500">Toplam Ciro</div>
                <div className="text-lg font-semibold text-indigo-700" data-testid="history-revenue">
                  {formatMoney(data.total_revenue)}
                </div>
              </div>
            </div>

            {data.history.length === 0 ? (
              <EmptyState message="Bu urun henuz hic satilmamis." />
            ) : (
              <div className="overflow-x-auto border border-gray-200 rounded">
                <table className="w-full text-sm" data-testid="history-table">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Satis</th>
                      <th className="text-left px-3 py-2 font-medium">Tarih</th>
                      <th className="text-left px-3 py-2 font-medium">Musteri</th>
                      <th className="text-right px-3 py-2 font-medium">Miktar</th>
                      <th className="text-right px-3 py-2 font-medium">Tutar</th>
                      <th className="text-left px-3 py-2 font-medium">Durum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.history.map((h, i) => (
                      <tr key={`${h.sale_id}-${i}`} className="border-t border-gray-100">
                        <td className="px-3 py-2">
                          <Link
                            to={`/sales/${h.sale_id}`}
                            className="text-indigo-600 hover:underline"
                          >
                            #{h.sale_id}
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-gray-600">{formatDate(h.sale_date)}</td>
                        <td className="px-3 py-2 text-gray-800">{h.customer_name}</td>
                        <td className="px-3 py-2 text-right">{h.quantity}</td>
                        <td className="px-3 py-2 text-right font-medium">
                          {formatMoney(h.total_price)}
                        </td>
                        <td className="px-3 py-2">
                          <Badge tone={statusTone[h.status] ?? 'gray'}>
                            {statusLabel[h.status] ?? h.status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="text-xs text-gray-400 mt-2">
              Toplam satilan ve ciro, iptal edilen satislari icermez.
            </p>
          </>
        ) : null}

        <div className="mt-4 text-right">
          <Button variant="secondary" onClick={onClose} data-testid="history-close">
            Kapat
          </Button>
        </div>
      </div>
    </div>
  );
}
