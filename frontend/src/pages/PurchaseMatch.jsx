import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Badge,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatMoney,
  formatQty,
} from '../components/ui';
import { purchaseOrderAPI } from '../services/api';

function DiffCell({ value, differs, children }) {
  return (
    <td
      className={`px-4 py-2 text-right ${
        differs ? 'bg-amber-50 text-amber-800 font-medium' : 'text-gray-700'
      }`}
    >
      {children ?? value}
    </td>
  );
}

export default function PurchaseMatch() {
  const { id } = useParams();
  const [match, setMatch] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setMatch(await purchaseOrderAPI.match(Number(id)));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div data-testid="page-PurchaseMatch">
      <PageHeader title="Uclu Eslestirme" />
      <ErrorMessage message={error} onRetry={load} />

      {loading ? (
        <Loading />
      ) : !match ? (
        <EmptyState message="Eslestirme verisi bulunamadi." />
      ) : (
        <>
          <div className="bg-white border border-gray-200 rounded p-4 mb-4 flex flex-wrap items-center gap-4">
            <div>
              <div className="text-xs text-gray-500">Siparis No</div>
              <div className="font-mono text-gray-800">{match.po_number ?? `#${match.purchase_order_id}`}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Teslim Durumu</div>
              <div className="text-gray-800">{match.status}</div>
            </div>
            <div className="ml-auto">
              {match.has_difference ? (
                <Badge tone="yellow">Fark var</Badge>
              ) : (
                <Badge tone="green">Fark yok</Badge>
              )}
            </div>
          </div>

          {match.rows.length === 0 ? (
            <EmptyState message="Bu siparisin kalemi yok." />
          ) : (
            <div className="bg-white border border-gray-200 rounded overflow-x-auto">
              <table className="w-full text-sm" data-testid="purchase-match-table">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium" rowSpan={2}>
                      Urun
                    </th>
                    <th className="text-center px-4 py-1 font-medium border-l border-gray-200" colSpan={3}>
                      Miktar
                    </th>
                    <th className="text-center px-4 py-1 font-medium border-l border-gray-200" colSpan={3}>
                      Birim Fiyat
                    </th>
                  </tr>
                  <tr className="text-xs">
                    <th className="text-right px-4 py-1 font-medium border-l border-gray-200">
                      Siparis
                    </th>
                    <th className="text-right px-4 py-1 font-medium">Kabul</th>
                    <th className="text-right px-4 py-1 font-medium">Fatura</th>
                    <th className="text-right px-4 py-1 font-medium border-l border-gray-200">
                      Siparis
                    </th>
                    <th className="text-right px-4 py-1 font-medium">Kabul</th>
                    <th className="text-right px-4 py-1 font-medium">Fatura</th>
                  </tr>
                </thead>
                <tbody>
                  {match.rows.map((row) => (
                    <tr
                      key={row.product_id}
                      className="border-t border-gray-100"
                      data-testid={`match-row-${row.product_id}`}
                    >
                      <td className="px-4 py-2 text-gray-800">{row.product_name}</td>
                      <td className="px-4 py-2 text-right text-gray-700 border-l border-gray-200">
                        {formatQty(row.ordered_quantity)}
                      </td>
                      <DiffCell differs={row.quantity_difference}>
                        {formatQty(row.received_quantity)}
                      </DiffCell>
                      <DiffCell differs={row.quantity_difference}>
                        {formatQty(row.invoiced_quantity)}
                      </DiffCell>
                      <td className="px-4 py-2 text-right text-gray-700 border-l border-gray-200">
                        {formatMoney(row.order_unit_price)}
                      </td>
                      <td className="px-4 py-2 text-right text-gray-700">
                        {row.receipt_unit_price == null
                          ? '-'
                          : formatMoney(row.receipt_unit_price)}
                      </td>
                      <DiffCell differs={row.price_difference}>
                        {row.invoice_unit_price == null
                          ? '-'
                          : formatMoney(row.invoice_unit_price)}
                      </DiffCell>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
