import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import SalesForm from '../components/SalesForm';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  formatMoney,
} from '../components/ui';
import { salesAPI } from '../services/api';

export const statusTone = {
  pending: 'yellow',
  completed: 'green',
  cancelled: 'red',
};

export const statusLabel = {
  pending: 'Bekliyor',
  completed: 'Tamamlandi',
  cancelled: 'Iptal',
};

export default function Sales() {
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setSales(await salesAPI.getAll());
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
    <div data-testid="page-Sales">
      <PageHeader title="Satislar">
        <Button onClick={() => setFormOpen(true)} data-testid="new-sale">
          + Yeni Satis
        </Button>
      </PageHeader>

      <ErrorMessage message={error} onRetry={load} />

      {formOpen && (
        <SalesForm
          onCreated={(sale) => {
            setFormOpen(false);
            navigate(`/sales/${sale.id}`);
          }}
          onCancel={() => setFormOpen(false)}
        />
      )}

      {loading ? (
        <Loading />
      ) : sales.length === 0 ? (
        <EmptyState message="Henuz satis yok." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="sales-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">No</th>
                <th className="text-left px-4 py-2 font-medium">Musteri</th>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-right px-4 py-2 font-medium">Urun Sayisi</th>
                <th className="text-right px-4 py-2 font-medium">Tutar</th>
                <th className="text-left px-4 py-2 font-medium">Durum</th>
                <th className="text-right px-4 py-2 font-medium">Islem</th>
              </tr>
            </thead>
            <tbody>
              {sales.map((s) => (
                <tr key={s.id} data-testid={`sale-row-${s.id}`} className="border-t border-gray-100">
                  <td className="px-4 py-2 text-gray-500">#{s.id}</td>
                  <td className="px-4 py-2 text-gray-800">{s.customer?.name ?? '-'}</td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(s.sale_date)}</td>
                  <td className="px-4 py-2 text-right text-gray-600">{s.items?.length ?? 0}</td>
                  <td className="px-4 py-2 text-right font-medium text-gray-800">
                    {formatMoney(s.total_amount)}
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={statusTone[s.status] ?? 'gray'}>
                      {statusLabel[s.status] ?? s.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      to={`/sales/${s.id}`}
                      data-testid={`detail-${s.id}`}
                      className="text-indigo-600 hover:underline"
                    >
                      Detay
                    </Link>
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
