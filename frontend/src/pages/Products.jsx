import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import FilterBar, { FilterField, SearchInput, SelectFilter, SortableTh } from '../components/FilterBar';
import ProductDetailModal from '../components/Products/ProductDetailModal';
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
  formatQty,
  inputClass,
  qty,
} from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { brandAPI, itemGroupAPI, productAPI } from '../services/api';
import { matches, sortRows, toggleSort } from '../utils/filters';

const LOW_STOCK = 10;

// Phase 10: stok backend'de ledger toplamindan hesaplaniyor ve ondalik
// (Numeric) olarak geliyor; karsilastirmalar qty() ile sayiya cevrilir.
function stockBadge(stock) {
  const n = qty(stock);
  if (n <= 0) return <Badge tone="red">Tukendi</Badge>;
  if (n < LOW_STOCK) return <Badge tone="yellow">Az stok</Badge>;
  return <Badge tone="green">Yeterli</Badge>;
}

const STOCK_OPTIONS = [
  { value: 'all', label: 'Tum stok durumlari' },
  { value: 'ok', label: 'Yeterli (10+)' },
  { value: 'low', label: 'Az stok (1-9)' },
  { value: 'out', label: 'Tukendi (0)' },
];

// Phase 13: agac yapisindaki kategoriler <select> icin girintili duz listeye
// cevrilir; bir ust kategori secildiginde alt kategorilerin urunleri de gorunur.
function flattenGroups(nodes, depth = 0, out = []) {
  for (const node of nodes) {
    out.push({ id: node.id, name: node.name, depth });
    flattenGroups(node.children ?? [], depth + 1, out);
  }
  return out;
}

/** Secilen kategori ve tum alt kategorilerinin id kumesi. */
function groupWithDescendants(nodes, targetId) {
  for (const node of nodes) {
    if (node.id === targetId) {
      const ids = [];
      const walk = (n) => {
        ids.push(n.id);
        (n.children ?? []).forEach(walk);
      };
      walk(node);
      return new Set(ids);
    }
    const found = groupWithDescendants(node.children ?? [], targetId);
    if (found) return found;
  }
  return null;
}

function stockGroup(stock) {
  const n = qty(stock);
  if (n <= 0) return 'out';
  if (n < LOW_STOCK) return 'low';
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
  const [detail, setDetail] = useState(null);

  // Phase 8: arama, stok filtresi, siralama
  // Phase 9 entegrasyonu: uyari panelinden /products?stock=low ile gelinebiliyor
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [stockFilter, setStockFilter] = useState(searchParams.get('stock') ?? 'all');
  const [sort, setSort] = useState({ key: null, dir: 'asc' });

  // Phase 13: kategori/marka filtresi ve barkod arama
  const [groupTree, setGroupTree] = useState([]);
  const [brands, setBrands] = useState([]);
  const [groupFilter, setGroupFilter] = useState('all');
  const [brandFilter, setBrandFilter] = useState('all');
  const [barcode, setBarcode] = useState('');
  const [barcodeHit, setBarcodeHit] = useState(null);

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

  // Katalog verisi listeden bagimsiz, bir kez yuklenir. Katalog bos olabilir
  // (Phase 13 oncesi kurulum) - o durumda filtreler gizlenir, hata gosterilmez.
  useEffect(() => {
    Promise.all([itemGroupAPI.tree(), brandAPI.getAll()])
      .then(([tree, brandList]) => {
        setGroupTree(tree);
        setBrands(brandList);
      })
      .catch(() => {
        setGroupTree([]);
        setBrands([]);
      });
  }, []);

  // URL'den gelen filtre degisirse (uyari panelinden gelis) state'i guncelle
  useEffect(() => {
    const fromUrl = searchParams.get('stock');
    if (fromUrl && fromUrl !== stockFilter) setStockFilter(fromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Ust kategori secilirse alt kategorilerin urunleri de listede kalir
  const groupIds = useMemo(
    () =>
      groupFilter === 'all'
        ? null
        : groupWithDescendants(groupTree, Number(groupFilter)),
    [groupTree, groupFilter]
  );

  const visible = useMemo(() => {
    const filtered = products.filter(
      (p) =>
        matches(p, ['name', 'sku'], search) &&
        (stockFilter === 'all' || stockGroup(p.stock) === stockFilter) &&
        (groupIds === null || groupIds.has(p.item_group_id)) &&
        (brandFilter === 'all' || p.brand_id === Number(brandFilter))
    );
    return sortRows(filtered, sort, ['price', 'stock', 'id']);
  }, [products, search, stockFilter, groupIds, brandFilter, sort]);

  const hasFilters =
    search.trim() !== ''
    || stockFilter !== 'all'
    || groupFilter !== 'all'
    || brandFilter !== 'all'
    || Boolean(sort.key);

  const clearFilters = () => {
    setSearch('');
    setStockFilter('all');
    setGroupFilter('all');
    setBrandFilter('all');
    setSort({ key: null, dir: 'asc' });
    if (searchParams.get('stock')) setSearchParams({}, { replace: true });
  };

  /**
   * Barkod okuyucu klavye emulasyonuyla calisir: okuma Enter ile biter.
   * Bulunan urun listede tek basina gosterilsin diye arama kutusuna SKU yazilir.
   */
  const searchBarcode = async (event) => {
    event.preventDefault();
    const value = barcode.trim();
    if (!value) return;
    setError('');
    setBarcodeHit(null);
    try {
      const hit = await productAPI.byBarcode(value);
      setBarcodeHit(hit);
      setSearch(hit.product.sku);
      setStockFilter('all');
      setGroupFilter('all');
      setBrandFilter('all');
    } catch {
      setBarcodeHit({ notFound: true });
    } finally {
      setBarcode('');
    }
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
          {groupTree.length > 0 && (
            <FilterField label="Kategori">
              <SelectFilter
                value={groupFilter}
                onChange={setGroupFilter}
                options={[
                  { value: 'all', label: 'Tum kategoriler' },
                  ...flattenGroups(groupTree).map((g) => ({
                    value: String(g.id),
                    // <option> bosluklari kirpar; girinti icin sert bosluk gerekir
                    label: `${'  '.repeat(g.depth)}${g.name}`,
                  })),
                ]}
                testid="group-filter"
              />
            </FilterField>
          )}
          {brands.length > 0 && (
            <FilterField label="Marka">
              <SelectFilter
                value={brandFilter}
                onChange={setBrandFilter}
                options={[
                  { value: 'all', label: 'Tum markalar' },
                  ...brands.map((b) => ({ value: String(b.id), label: b.name })),
                ]}
                testid="brand-filter"
              />
            </FilterField>
          )}
          <FilterField label="Barkod">
            <form onSubmit={searchBarcode}>
              <input
                type="text"
                value={barcode}
                onChange={(e) => setBarcode(e.target.value)}
                placeholder="Okutun veya yazip Enter"
                data-testid="barcode-search"
                className={`${inputClass} min-w-[200px]`}
              />
            </form>
          </FilterField>
        </FilterBar>
      )}

      {barcodeHit && (
        <div
          data-testid="barcode-result"
          className={`text-sm rounded px-3 py-2 mb-4 border ${
            barcodeHit.notFound
              ? 'text-red-700 bg-red-50 border-red-200'
              : 'text-indigo-700 bg-indigo-50 border-indigo-200'
          }`}
        >
          {barcodeHit.notFound
            ? 'Bu barkodla eslesen urun bulunamadi.'
            : `Barkod: ${barcodeHit.product.name}`
              + (barcodeHit.uom_code ? ` (${barcodeHit.uom_code})` : '')}
        </div>
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
                  onClick={() => setDetail(p)}
                  className={`border-t border-gray-100 cursor-pointer hover:bg-gray-50 ${
                    qty(p.stock) <= 0
                      ? 'bg-red-50'
                      : qty(p.stock) < LOW_STOCK
                        ? 'bg-yellow-50'
                        : ''
                  }`}
                >
                  <td className="px-4 py-2 text-gray-800">
                    {p.name}
                    {(p.item_group_name || p.brand_name) && (
                      <div className="text-xs text-gray-400">
                        {[p.item_group_name, p.brand_name].filter(Boolean).join(' · ')}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 text-gray-500 font-mono text-xs">{p.sku}</td>
                  <td className="px-4 py-2 text-right text-gray-800">{formatMoney(p.price)}</td>
                  <td
                    className="px-4 py-2 text-right font-medium text-gray-800"
                    data-testid={`stock-${p.id}`}
                  >
                    {formatQty(p.stock)}
                  </td>
                  <td className="px-4 py-2">{stockBadge(p.stock)}</td>
                  <td
                    className="px-4 py-2 text-right whitespace-nowrap"
                    onClick={(e) => e.stopPropagation()}
                  >
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

      {detail && <ProductDetailModal product={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
