import { useCallback, useEffect, useState } from 'react';
import FilterBar, { FilterField, SelectFilter } from '../components/FilterBar';
import {
  Badge,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  formatQty,
  inputClass,
  qty,
} from '../components/ui';
import { productAPI, stockAPI, warehouseAPI } from '../services/api';

const REASONS = [
  { value: '', label: 'Tum nedenler' },
  { value: 'acilis', label: 'Acilis' },
  { value: 'satis', label: 'Satis' },
  { value: 'satis_iptal', label: 'Satis iptali' },
  { value: 'alim', label: 'Alim' },
  { value: 'alim_iade', label: 'Alim iadesi' },
  { value: 'transfer_giris', label: 'Transfer girisi' },
  { value: 'transfer_cikis', label: 'Transfer cikisi' },
  { value: 'sayim', label: 'Sayim' },
  { value: 'fire', label: 'Fire' },
  { value: 'duzeltme', label: 'Duzeltme' },
];

const reasonLabel = Object.fromEntries(REASONS.map((r) => [r.value, r.label]));

/** Stok hareket dokumu (Phase 10). Filtreler backend'e parametre olarak gider. */
export default function StockLedger() {
  const [entries, setEntries] = useState([]);
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [productId, setProductId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [reason, setReason] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    Promise.all([productAPI.getAll({ limit: 500 }), warehouseAPI.getAll()])
      .then(([p, w]) => {
        setProducts(p);
        setWarehouses(w);
      })
      .catch((err) => setError(err.message));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = {};
      if (productId) params.product_id = productId;
      if (warehouseId) params.warehouse_id = warehouseId;
      if (reason) params.reason = reason;
      if (dateFrom) params.from = dateFrom;
      if (dateTo) params.to = dateTo;
      setEntries(await stockAPI.ledger(params));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [productId, warehouseId, reason, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  const hasFilters = Boolean(productId || warehouseId || reason || dateFrom || dateTo);
  const clearFilters = () => {
    setProductId('');
    setWarehouseId('');
    setReason('');
    setDateFrom('');
    setDateTo('');
  };

  return (
    <div data-testid="page-StockLedger">
      <PageHeader title="Stok Hareketleri" />
      <ErrorMessage message={error} onRetry={load} />

      <FilterBar
        resultCount={entries.length}
        totalCount={entries.length}
        hasFilters={hasFilters}
        onClear={clearFilters}
      >
        <FilterField label="Urun">
          <SelectFilter
            value={productId}
            onChange={setProductId}
            options={[
              { value: '', label: 'Tum urunler' },
              ...products.map((p) => ({ value: String(p.id), label: p.name })),
            ]}
            testid="ledger-product"
          />
        </FilterField>
        <FilterField label="Depo">
          <SelectFilter
            value={warehouseId}
            onChange={setWarehouseId}
            options={[
              { value: '', label: 'Tum depolar' },
              ...warehouses.map((w) => ({ value: String(w.id), label: w.name })),
            ]}
            testid="ledger-warehouse"
          />
        </FilterField>
        <FilterField label="Neden">
          <SelectFilter
            value={reason}
            onChange={setReason}
            options={REASONS}
            testid="ledger-reason"
          />
        </FilterField>
        <FilterField label="Baslangic">
          <input
            type="date"
            className={inputClass}
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            data-testid="ledger-from"
          />
        </FilterField>
        <FilterField label="Bitis">
          <input
            type="date"
            className={inputClass}
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            data-testid="ledger-to"
          />
        </FilterField>
      </FilterBar>

      {loading ? (
        <Loading />
      ) : entries.length === 0 ? (
        <EmptyState message="Bu kriterlere uyan stok hareketi yok." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="ledger-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-left px-4 py-2 font-medium">Urun</th>
                <th className="text-left px-4 py-2 font-medium">Depo</th>
                <th className="text-left px-4 py-2 font-medium">Neden</th>
                <th className="text-left px-4 py-2 font-medium">Belge</th>
                <th className="text-right px-4 py-2 font-medium">Hareket</th>
                <th className="text-right px-4 py-2 font-medium">Bakiye</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr
                  key={e.id}
                  className="border-t border-gray-100"
                  data-testid={`ledger-row-${e.id}`}
                >
                  <td className="px-4 py-2 text-gray-600">{formatDate(e.created_at)}</td>
                  <td className="px-4 py-2 text-gray-800">
                    {e.product_name}
                    <span className="font-mono text-xs text-gray-400 ml-2">
                      {e.product_sku}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-700">{e.warehouse_name ?? '-'}</td>
                  <td className="px-4 py-2">
                    <Badge tone={qty(e.change_qty) < 0 ? 'yellow' : 'green'}>
                      {reasonLabel[e.reason] ?? e.reason}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500">
                    {e.ref_type && e.ref_id ? `${e.ref_type} #${e.ref_id}` : '-'}
                  </td>
                  <td
                    className={`px-4 py-2 text-right font-medium ${
                      qty(e.change_qty) < 0 ? 'text-red-600' : 'text-green-700'
                    }`}
                  >
                    {qty(e.change_qty) > 0 ? '+' : ''}
                    {formatQty(e.change_qty)}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-800">
                    {formatQty(e.balance_qty)}
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
