import { formatDate } from '../Dashboard/utils/dateUtils';
import { Badge, EmptyState, formatMoney } from '../ui';

const STATUS_LABEL = { pending: 'Beklemede', processing: 'Hazirlaniyor', delivered: 'Teslim Edildi' };
const STATUS_TONE = { pending: 'yellow', processing: 'blue', delivered: 'green' };

/**
 * Phase 17: Musteri/Urun detay modal'larinin siparis tablolarinda ortak kullanilir.
 * secondColumn: { label: 'Urun' | 'Musteri', field: 'product' | 'customer' }
 */
export default function OrdersTable({ orders, secondColumn, emptyMessage }) {
  if (!orders || orders.length === 0) {
    return <EmptyState message={emptyMessage ?? 'Siparis bulunamadi.'} />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="orders-table">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            <th className="text-left px-4 py-2 font-medium">Siparis No</th>
            <th className="text-left px-4 py-2 font-medium">{secondColumn.label}</th>
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
              <td className="px-4 py-2 text-gray-600">{o[secondColumn.field]}</td>
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
  );
}
