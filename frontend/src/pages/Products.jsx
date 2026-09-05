import { useCallback, useEffect, useState } from 'react';
import ProductForm from '../components/ProductForm';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatMoney,
} from '../components/ui';
import { productAPI } from '../services/api';

const LOW_STOCK = 10;

function stockBadge(stock) {
  if (stock === 0) return <Badge tone="red">Tukendi</Badge>;
  if (stock < LOW_STOCK) return <Badge tone="yellow">Az stok</Badge>;
  return <Badge tone="green">Yeterli</Badge>;
}

export default function Products() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [notice, setNotice] = useState('');

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

      {loading ? (
        <Loading />
      ) : products.length === 0 ? (
        <EmptyState message="Henuz urun yok." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="products-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Urun</th>
                <th className="text-left px-4 py-2 font-medium">SKU</th>
                <th className="text-right px-4 py-2 font-medium">Fiyat</th>
                <th className="text-right px-4 py-2 font-medium">Stok</th>
                <th className="text-left px-4 py-2 font-medium">Durum</th>
                <th className="text-right px-4 py-2 font-medium">Islemler</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
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
                      onClick={() => {
                        setEditing(p);
                        setFormOpen(true);
                      }}
                      data-testid={`edit-${p.id}`}
                    >
                      Duzenle
                    </Button>
                    <Button variant="danger" onClick={() => remove(p)} data-testid={`delete-${p.id}`}>
                      Sil
                    </Button>
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
