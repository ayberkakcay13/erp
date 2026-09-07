import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { reportAPI, stockAPI } from '../services/api';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  formatDate,
  formatMoney,
  formatQty,
  qty,
} from './ui';

const statusTone = { pending: 'yellow', completed: 'green', cancelled: 'red' };
const statusLabel = { pending: 'Bekliyor', completed: 'Tamamlandi', cancelled: 'Iptal' };

// Phase 10: stok defteri hareket nedenleri
const reasonLabel = {
  acilis: 'Acilis',
  satis: 'Satis',
  satis_iptal: 'Satis iptali',
  alim: 'Alim',
  alim_iade: 'Alim iadesi',
  transfer_giris: 'Transfer girisi',
  transfer_cikis: 'Transfer cikisi',
  sayim: 'Sayim',
  fire: 'Fire',
  duzeltme: 'Duzeltme',
};

function reasonTone(reason, change) {
  if (reason === 'fire') return 'red';
  return qty(change) < 0 ? 'yellow' : 'green';
}

function StockTab({ data }) {
  if (!data) return <Loading />;
  return (
    <>
      <div className="mb-4">
        <div className="text-xs text-gray-500 mb-1">Depo bazinda stok</div>
        {data.by_warehouse.length === 0 ? (
          <p className="text-sm text-gray-500">Bu urunun hic stok hareketi yok.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {data.by_warehouse.map((row) => (
              <span
                key={row.warehouse_id}
                className="text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1"
              >
                {row.warehouse_name ?? `Depo #${row.warehouse_id}`}:{' '}
                <b>{formatQty(row.quantity)}</b>
              </span>
            ))}
          </div>
        )}
      </div>

      {data.entries.length === 0 ? (
        <EmptyState message="Bu urunun stok hareketi yok." />
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded">
          <table className="w-full text-sm" data-testid="stock-history-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Tarih</th>
                <th className="text-left px-3 py-2 font-medium">Neden</th>
                <th className="text-left px-3 py-2 font-medium">Depo</th>
                <th className="text-left px-3 py-2 font-medium">Belge</th>
                <th className="text-right px-3 py-2 font-medium">Hareket</th>
                <th className="text-right px-3 py-2 font-medium">Bakiye</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.id} className="border-t border-gray-100">
                  <td className="px-3 py-2 text-gray-600">{formatDate(e.created_at)}</td>
                  <td className="px-3 py-2">
                    <Badge tone={reasonTone(e.reason, e.change_qty)}>
                      {reasonLabel[e.reason] ?? e.reason}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-gray-700">{e.warehouse_name ?? '-'}</td>
                  <td className="px-3 py-2 text-gray-500 text-xs">
                    {e.ref_type && e.ref_id ? `${e.ref_type} #${e.ref_id}` : '-'}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-medium ${
                      qty(e.change_qty) < 0 ? 'text-red-600' : 'text-green-700'
                    }`}
                  >
                    {qty(e.change_qty) > 0 ? '+' : ''}
                    {formatQty(e.change_qty)}
                  </td>
                  <td className="px-3 py-2 text-right text-gray-800">
                    {formatQty(e.balance_qty)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-gray-400 mt-2">
        Stok defteri satirlari degistirilmez; duzeltmeler yeni satir olarak eklenir.
      </p>
    </>
  );
}

function SalesTab({ data }) {
  if (!data) return <Loading />;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-gray-50 rounded p-3">
          <div className="text-xs text-gray-500">Toplam Satilan</div>
          <div className="text-lg font-semibold text-gray-800" data-testid="history-sold">
            {formatQty(data.total_sold)}
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
                  <td className="px-3 py-2 text-right">{formatQty(h.quantity)}</td>
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
  );
}

/**
 * Urun detay penceresi.
 * Phase 10 ile birlikte iki sekme var: stok defteri hareketleri (yeni) ve
 * satis gecmisi (eskiden beri var olan icerik).
 */
export default function ProductHistoryModal({ productId, onClose }) {
  const [tab, setTab] = useState('stock');
  const [stock, setStock] = useState(null);
  const [sales, setSales] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([stockAPI.productHistory(productId), reportAPI.productHistory(productId)])
      .then(([stockData, salesData]) => {
        if (cancelled) return;
        setStock(stockData);
        setSales(salesData);
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [productId]);

  const tabClass = (key) =>
    `px-3 py-1.5 text-sm rounded-t border-b-2 transition-colors ${
      tab === key
        ? 'border-indigo-600 text-indigo-700 font-medium'
        : 'border-transparent text-gray-500 hover:text-gray-700'
    }`;

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-10"
      onClick={onClose}
      data-testid="product-history-modal"
    >
      <div
        className="bg-white rounded shadow-lg max-w-3xl w-full max-h-[85vh] overflow-auto p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <ErrorMessage message={error} />
        {!stock && !error ? (
          <Loading />
        ) : stock ? (
          <>
            <h3 className="text-lg font-semibold text-gray-800">{stock.product_name}</h3>
            <p className="font-mono text-xs text-gray-500 mb-3">{stock.sku}</p>

            <div className="bg-gray-50 rounded p-3 mb-4 inline-block">
              <div className="text-xs text-gray-500">Mevcut Stok (tum depolar)</div>
              <div className="text-lg font-semibold text-gray-800" data-testid="history-stock">
                {formatQty(stock.total_stock)}
              </div>
            </div>

            <div className="flex gap-2 border-b border-gray-200 mb-4">
              <button
                type="button"
                className={tabClass('stock')}
                onClick={() => setTab('stock')}
                data-testid="tab-stock"
              >
                Stok Hareketleri
              </button>
              <button
                type="button"
                className={tabClass('sales')}
                onClick={() => setTab('sales')}
                data-testid="tab-sales"
              >
                Satis Gecmisi
              </button>
            </div>

            {tab === 'stock' ? <StockTab data={stock} /> : <SalesTab data={sales} />}
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
