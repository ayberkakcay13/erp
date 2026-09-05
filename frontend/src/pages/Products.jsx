import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import FilterBar, { FilterField, SearchInput, SelectFilter, SortableTh } from '../components/FilterBar';
import ProductForm from '../components/ProductForm';
import ProductHistoryModal from '../components/ProductHistoryModal';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatMoney,
} from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { productAPI } from '../services/api';
import { matches, sortRows, toggleSort } from '../utils/filters';

const LOW_STOCK = 10;

function stockBadge(stock) {
  if (stock === 0) return <Badge tone="red">Tukendi</Badge>;
  if (stock < LOW_STOCK) return <Badge tone="yellow">Az stok</Badge>;
  return <Badge tone="green">Yeterli</Badge>;
}

const STOCK_OPTIONS = [
  { value: 'all', label: 'Tum stok durumlari' },
  { value: 'ok', label: 'Yeterli (10+)' },
  { value: 'low', label: 'Az stok (1-9)' },
  { value: 'out', label: 'Tukendi (0)' },
];

function stockGroup(stock) {
  if (stock === 0) return 'out';
  if (stock < LOW_STOCK) return 'low';
  return 'ok';
}

export default function Products() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [notice, setNotice] = useState('');
  const { isAdmin } = useAuth();
  const [historyId, setHistoryId] = useState(null);

  // Phase 8: arama, stok filtresi, siralama
  // Phase 9 entegrasyonu: uyari panelinden /products?stock=low ile gelinebiliyor
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [stockFilter, setStockFilter] = useState(searchParams.get('stock') ?? 'all');
  const [sort, setSort] = useState({ key: null, dir: 'asc' });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setProducts(await productAPI.getAll());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // URL'den gelen filtre degisirse (uyari panelinden gelis) state'i guncelle
  useEffect(() => {
    const fromUrl = searchParams.get('stock');
    if (fromUrl && fromUrl !== stockFilter) setStockFilter(fromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const visible = useMemo(() => {
    const filtered = products.filter(
      (p) =>
        matches(p, ['name', 'sku'], search) &&
        (stockFilter === 'all' || stockGroup(p.stock) === stockFilter)
    );
    return sortRows(filtered, sort, ['price', 'stock', 'id']);
  }, [products, search, stockFilter, sort]);

  const hasFilters = search.trim() !== '' || stockFilter !== 'all' || Boolean(sort.key);

  const clearFilters = () => {
    setSearch('');
    setStockFilter('all');
    setSort({ key: null, dir: 'asc' });
    if (searchParams.get('stock')) setSearchParams({}, { replace: true });
  };

  const handleSaved = (saved) => {
    setFormOpen(false);
    setEditing(null);
    setNotice(`"${saved.name}" kaydedildi.`);
    load();
  };

  const remove = async (product) => {
    if (!window.confirm(`"${product.name}" silinsin mi?`)) return;
    setError('');
    try {
      await productAPI.delete(product.id);
      setNotice(`"${product.name}" silindi.`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const onSort = (k) => setSort(toggleSort(sort, k));

  return (
    <div data-testid="page-Products">
      <PageHeader title="Urunler">
        <Button
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
          data-testid="new-product"
        >
          + Yeni Urun
        </Button>
      </PageHeader>

      <ErrorMessage message={error} onRetry={load} />
      {notice && (
        <div data-testid="notice" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-4">
          {notice}
        </div>
      )}

      {formOpen && (
        <ProductForm
          product={editing}
          onSaved={handleSaved}
          onCancel={() => {
            setFormOpen(false);
            setEditing(null);
          }}
        />
      )}

      {!loading && (
        <FilterBar
          resultCount={visible.length}
          totalCount={products.length}
          hasFilters={hasFilters}
          onClear={clearFilters}
        >
          <FilterField label="Ara">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Urun adi veya SKU"
              testid="product-search"
            />
          </FilterField>
          <FilterField label="Stok durumu">
            <SelectFilter
              value={stockFilter}
              onChange={setStockFilter}
              options={STOCK_OPTIONS}
              testid="stock-filter"
            />
          </FilterField>
        </FilterBar>
      )}

      {loading ? (
        <Loading />
      ) : products.length === 0 ? (
        <EmptyState message="Henuz urun yok." />
      ) : visible.length === 0 ? (
        <EmptyState message="Arama/filtre kriterlerine uyan urun bulunamadi." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="products-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <SortableTh label="Urun" sortKey="name" sort={sort} onSort={onSort} />
                <SortableTh label="SKU" sortKey="sku" sort={sort} onSort={onSort} />
                <SortableTh label="Fiyat" sortKey="price" sort={sort} onSort={onSort} align="right" />
                <SortableTh label="Stok" sortKey="stock" sort={sort} onSort={onSort} align="right" />
                <th className="text-left px-4 py-2 font-medium">Durum</th>
                <th className="text-right px-4 py-2 font-medium">Islemler</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((p) => (
                <tr
                  key={p.id}
                  data-testid={`product-row-${p.id}`}
                  className={`border-t border-gray-100 ${
                    p.stock === 0 ? 'bg-red-50' : p.stock < LOW_STOCK ? 'bg-yellow-50' : ''
                  }`}
                >
                  <td className="px-4 py-2 text-gray-800">{p.name}</td>
                  <td className="px-4 py-2 text-gray-500 font-mono text-xs">{p.sku}</td>
                  <td className="px-4 py-2 text-right text-gray-800">{formatMoney(p.price)}</td>
                  <td
                    className="px-4 py-2 text-right font-medium text-gray-800"
                    data-testid={`stock-${p.id}`}
                  >
                    {p.stock}
                  </td>
                  <td className="px-4 py-2">{stockBadge(p.stock)}</td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <Button
                      variant="secondary"
                      className="mr-2"
                      onClick={() => setHistoryId(p.id)}
                      data-testid={`history-${p.id}`}
                    >
                      Gecmis
                    </Button>
                    <Button
                      variant="secondary"
                      className="mr-2"
                      onClick={() => {
                        setEditing(p);
                        setFormOpen(true);
                      }}
                      data-testid={`edit-${p.id}`}
                    >
                      Duzenle
                    </Button>
                    {/* Silme sadece admin rolunde gorunur (backend de 403 ile korur) */}
                    {isAdmin && (
                      <Button variant="danger" onClick={() => remove(p)} data-testid={`delete-${p.id}`}>
                        Sil
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {historyId && (
        <ProductHistoryModal productId={historyId} onClose={() => setHistoryId(null)} />
      )}
    </div>
  );
}
