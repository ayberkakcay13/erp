import { useCallback, useEffect, useMemo, useState } from 'react';
import FilterBar, { FilterField, SearchInput, SelectFilter } from '../components/FilterBar';
import {
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatQty,
  qty,
} from '../components/ui';
import { stockAPI, warehouseAPI } from '../services/api';
import { matches } from '../utils/filters';

/**
 * Depo bazli stok durumu (Phase 10).
 * Satirlar urun x depo kiriliminda gelir; "Tum depolar" secilince
 * urun bazinda toplanip gosterilir.
 */
export default function StockBalance() {
  const [rows, setRows] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [warehouseId, setWarehouseId] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    warehouseAPI
      .getAll()
      .then(setWarehouses)
      .catch((err) => setError(err.message));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setRows(await stockAPI.balance(warehouseId ? { warehouse_id: warehouseId } : {}));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [warehouseId]);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    const filtered = rows.filter((r) => matches(r, ['product_name', 'sku'], search));
    if (warehouseId) return filtered;

    // Depo secilmediyse urun bazinda topla
    const byProduct = new Map();
    for (const row of filtered) {
      const existing = byProduct.get(row.product_id);
      if (existing) {
        existing.quantity = qty(existing.quantity) + qty(row.quantity);
        existing.warehouses.push(row);
      } else {
        byProduct.set(row.product_id, { ...row, warehouses: [row] });
      }
    }
    return [...byProduct.values()];
  }, [rows, search, warehouseId]);

  const total = visible.reduce((sum, r) => sum + qty(r.quantity), 0);

  return (
    <div data-testid="page-StockBalance">
      <PageHeader title="Stok Durumu" />
      <ErrorMessage message={error} onRetry={load} />

      <FilterBar
        resultCount={visible.length}
        totalCount={visible.length}
        hasFilters={Boolean(search || warehouseId)}
        onClear={() => {
          setSearch('');
          setWarehouseId('');
        }}
      >
        <FilterField label="Ara">
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Urun adi veya SKU"
            testid="balance-search"
          />
        </FilterField>
        <FilterField label="Depo">
          <SelectFilter
            value={warehouseId}
            onChange={setWarehouseId}
            options={[
              { value: '', label: 'Tum depolar (toplam)' },
              ...warehouses.map((w) => ({ value: String(w.id), label: w.name })),
            ]}
            testid="balance-warehouse"
          />
        </FilterField>
      </FilterBar>

      {loading ? (
        <Loading />
      ) : visible.length === 0 ? (
        <EmptyState message="Stok hareketi olan urun yok." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="balance-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Urun</th>
                <th className="text-left px-4 py-2 font-medium">SKU</th>
                <th className="text-left px-4 py-2 font-medium">
                  {warehouseId ? 'Depo' : 'Depolar'}
                </th>
                <th className="text-right px-4 py-2 font-medium">Miktar</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr
                  key={`${r.product_id}-${r.warehouse_id ?? 'all'}`}
                  className="border-t border-gray-100"
                  data-testid={`balance-row-${r.product_id}`}
                >
                  <td className="px-4 py-2 text-gray-800">{r.product_name}</td>
                  <td className="px-4 py-2 font-mono text-xs text-gray-500">{r.sku}</td>
                  <td className="px-4 py-2 text-gray-600 text-xs">
                    {warehouseId
                      ? r.warehouse_name
                      : (r.warehouses ?? [])
                          .map((w) => `${w.warehouse_name}: ${formatQty(w.quantity)}`)
                          .join(' · ')}
                  </td>
                  <td className="px-4 py-2 text-right font-medium text-gray-800">
                    {formatQty(r.quantity)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50 border-t border-gray-200">
              <tr>
                <td className="px-4 py-2 font-medium text-gray-700" colSpan={3}>
                  Toplam
                </td>
                <td
                  className="px-4 py-2 text-right font-semibold text-gray-800"
                  data-testid="balance-total"
                >
                  {formatQty(total)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
