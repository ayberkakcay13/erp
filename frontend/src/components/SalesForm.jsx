import { useEffect, useMemo, useState } from 'react';
import { conversionAPI, customerAPI, productAPI, salesAPI, uomAPI } from '../services/api';
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
  const [pickUom, setPickUom] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  // Phase 13: {id: uom} - satirlarda birim kodunu gostermek icin
  const [uoms, setUoms] = useState({});

  useEffect(() => {
    (async () => {
      try {
        const [c, p, u] = await Promise.all([
          customerAPI.getAll(),
          productAPI.getAll(),
          // Katalog kurulmamissa (Phase 13 oncesi) birim listesi bos kalir ve
          // form tek birimli eski davranisiyla calismaya devam eder.
          uomAPI.getAll({ is_active: true }).catch(() => []),
        ]);
        setCustomers(c);
        setProducts(p);
        setUoms(Object.fromEntries(u.map((item) => [item.id, item])));
      } catch (err) {
        setLoadError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selected = products.find((p) => String(p.id) === String(pickProduct));

  /** Urunun tanimli birimleri: satis, stok, alim (tekrarsiz). */
  const uomChoices = useMemo(() => {
    if (!selected) return [];
    const ids = [selected.sales_uom_id, selected.stock_uom_id, selected.purchase_uom_id];
    return [...new Set(ids.filter(Boolean))].map((id) => uoms[id]).filter(Boolean);
  }, [selected, uoms]);

  // Urun degisince varsayilan birim satis birimi (yoksa stok birimi) olsun
  useEffect(() => {
    setPickUom(selected ? String(selected.sales_uom_id ?? selected.stock_uom_id ?? '') : '');
  }, [selected]);

  const total = useMemo(
    () => items.reduce((sum, i) => sum + i.quantity * i.unit_price, 0),
    [items]
  );

  const addItem = async () => {
    setError('');
    const product = selected;
    const qty = Number(pickQty);
    if (!product) return setError('Once bir urun sec.');
    if (!qty || qty < 1) return setError('Miktar en az 1 olmali.');
    if (items.some((i) => i.product_id === product.id)) {
      return setError(`"${product.name}" zaten listede. Once listeden cikar.`);
    }

    // Ledger her zaman stok biriminde tutulur: girilen birim farkliysa
    // karsiligini simdiden hesapla. Donusum tanimli degilse backend 400 doner
    // ve kullanici hatayi satisi kaydetmeden once gorur.
    const uomId = pickUom ? Number(pickUom) : null;
    let stockQty = qty;
    if (uomId && product.stock_uom_id && uomId !== product.stock_uom_id) {
      try {
        const preview = await conversionAPI.preview({
          quantity: String(qty),
          from_uom_id: uomId,
          to_uom_id: product.stock_uom_id,
          product_id: product.id,
        });
        stockQty = Number(preview.converted);
      } catch (err) {
        return setError(err.message);
      }
    }

    setItems([
      ...items,
      {
        product_id: product.id,
        product_name: product.name,
        product_sku: product.sku,
        stock: product.stock,
        quantity: qty,
        uom_id: uomId,
        uom_code: uomId ? uoms[uomId]?.code : null,
        stock_quantity: stockQty,
        stock_uom_code: product.stock_uom_id ? uoms[product.stock_uom_id]?.code : null,
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
          uom_id: i.uom_id,
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
          {uomChoices.length > 1 && (
            <select
              value={pickUom}
              onChange={(e) => setPickUom(e.target.value)}
              data-testid="pick-uom"
              className={`${inputClass} w-28`}
            >
              {uomChoices.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.code}
                </option>
              ))}
            </select>
          )}
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
                    {i.stock_quantity > i.stock && (
                      <span className="ml-2 text-xs text-red-600">
                        (stokta {i.stock} var)
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {i.quantity}
                    {i.uom_code && <span className="text-gray-400 ml-1">{i.uom_code}</span>}
                    {/* Farkli birimde satis: stok karsiligi hemen gorunsun */}
                    {i.stock_quantity !== i.quantity && (
                      <div className="text-xs text-gray-400">
                        = {i.stock_quantity} {i.stock_uom_code}
                      </div>
                    )}
                  </td>
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
