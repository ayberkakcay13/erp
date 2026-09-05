import { useEffect, useMemo, useState } from 'react';
import { customerAPI, productAPI, salesAPI } from '../services/api';
import {
  Button,
  ErrorMessage,
  Field,
  Loading,
  formatMoney,
  inputClass,
} from './ui';

export default function SalesForm({ onCreated, onCancel }) {
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [customerId, setCustomerId] = useState('');
  const [saleDate, setSaleDate] = useState(new Date().toISOString().slice(0, 10));
  const [items, setItems] = useState([]);

  const [pickProduct, setPickProduct] = useState('');
  const [pickQty, setPickQty] = useState(1);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [c, p] = await Promise.all([customerAPI.getAll(), productAPI.getAll()]);
        setCustomers(c);
        setProducts(p);
      } catch (err) {
        setLoadError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const total = useMemo(
    () => items.reduce((sum, i) => sum + i.quantity * i.unit_price, 0),
    [items]
  );

  const addItem = () => {
    setError('');
    const product = products.find((p) => String(p.id) === String(pickProduct));
    const qty = Number(pickQty);
    if (!product) return setError('Once bir urun sec.');
    if (!qty || qty < 1) return setError('Miktar en az 1 olmali.');
    if (items.some((i) => i.product_id === product.id)) {
      return setError(`"${product.name}" zaten listede. Once listeden cikar.`);
    }
    setItems([
      ...items,
      {
        product_id: product.id,
        product_name: product.name,
        product_sku: product.sku,
        stock: product.stock,
        quantity: qty,
        unit_price: product.price,
      },
    ]);
    setPickProduct('');
    setPickQty(1);
  };

  const removeItem = (productId) =>
    setItems(items.filter((i) => i.product_id !== productId));

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!customerId) return setError('Musteri secmelisin.');
    if (items.length === 0) return setError('En az bir urun eklemelisin.');

    setSaving(true);
    try {
      const sale = await salesAPI.create({
        customer_id: Number(customerId),
        sale_date: saleDate,
        items: items.map((i) => ({
          product_id: i.product_id,
          quantity: i.quantity,
          unit_price: i.unit_price,
        })),
      });
      onCreated(sale, total);
    } catch (err) {
      // Stok yetersizse backend 400 doner, mesaji burada gosteriyoruz
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loading label="Musteri ve urunler yukleniyor..." />;
  if (loadError) return <ErrorMessage message={loadError} />;

  return (
    <form
      onSubmit={submit}
      data-testid="sales-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5"
    >
      <h3 className="font-medium text-gray-800 mb-3">Yeni satis</h3>
      <ErrorMessage message={error} />

      <div className="grid sm:grid-cols-2 gap-3 max-w-2xl">
        <Field label="Musteri">
          <select
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            data-testid="sale-customer"
            className={inputClass}
          >
            <option value="">-- Musteri sec --</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.email})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Satis Tarihi">
          <input
            type="date"
            value={saleDate}
            onChange={(e) => setSaleDate(e.target.value)}
            data-testid="sale-date"
            className={inputClass}
          />
        </Field>
      </div>

      <div className="border-t border-gray-100 mt-2 pt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Urun ekle</h4>
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[220px]">
            <select
              value={pickProduct}
              onChange={(e) => setPickProduct(e.target.value)}
              data-testid="pick-product"
              className={inputClass}
            >
              <option value="">-- Urun sec --</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {formatMoney(p.price)} (stok: {p.stock})
                </option>
              ))}
            </select>
          </div>
          <input
            type="number"
            min="1"
            value={pickQty}
            onChange={(e) => setPickQty(e.target.value)}
            data-testid="pick-qty"
            className={`${inputClass} w-24`}
          />
          <Button type="button" variant="secondary" onClick={addItem} data-testid="add-item">
            Ekle
          </Button>
        </div>
      </div>

      {items.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm" data-testid="items-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Urun</th>
                <th className="text-right px-3 py-2 font-medium">Miktar</th>
                <th className="text-right px-3 py-2 font-medium">Birim Fiyat</th>
                <th className="text-right px-3 py-2 font-medium">Satir Toplami</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.product_id} className="border-t border-gray-100" data-testid={`item-${i.product_id}`}>
                  <td className="px-3 py-2">
                    {i.product_name}
                    <span className="text-gray-400 text-xs ml-2 font-mono">{i.product_sku}</span>
                    {i.quantity > i.stock && (
                      <span className="ml-2 text-xs text-red-600">
                        (stokta {i.stock} var)
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">{i.quantity}</td>
                  <td className="px-3 py-2 text-right">{formatMoney(i.unit_price)}</td>
                  <td className="px-3 py-2 text-right font-medium">
                    {formatMoney(i.quantity * i.unit_price)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => removeItem(i.product_id)}
                      data-testid={`remove-${i.product_id}`}
                      className="text-red-600 hover:underline text-xs"
                    >
                      Cikar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-gray-200 bg-gray-50">
                <td colSpan={3} className="px-3 py-2 text-right font-medium text-gray-700">
                  Toplam
                </td>
                <td className="px-3 py-2 text-right font-semibold text-indigo-700" data-testid="form-total">
                  {formatMoney(total)}
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      <div className="flex gap-2 mt-4">
        <Button type="submit" disabled={saving} data-testid="sale-submit">
          {saving ? 'Kaydediliyor...' : 'Satisi Kaydet'}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Vazgec
        </Button>
      </div>
    </form>
  );
}
