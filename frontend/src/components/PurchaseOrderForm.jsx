import { useEffect, useMemo, useState } from 'react';
import {
  productAPI,
  purchaseOrderAPI,
  supplierAPI,
  uomAPI,
  warehouseAPI,
} from '../services/api';
import {
  Button,
  ErrorMessage,
  Field,
  Loading,
  formatMoney,
  inputClass,
} from './ui';

export default function PurchaseOrderForm({ onCreated, onCancel }) {
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [uoms, setUoms] = useState({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [supplierId, setSupplierId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [orderDate, setOrderDate] = useState(new Date().toISOString().slice(0, 10));
  const [expectedDate, setExpectedDate] = useState('');
  const [note, setNote] = useState('');
  const [items, setItems] = useState([]);

  const [pickProduct, setPickProduct] = useState('');
  const [pickQty, setPickQty] = useState(1);
  const [pickUom, setPickUom] = useState('');
  const [pickPrice, setPickPrice] = useState('');
  const [pickTax, setPickTax] = useState('20');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [s, p, w, u] = await Promise.all([
          supplierAPI.getAll({ is_active: true }),
          productAPI.getAll(),
          warehouseAPI.getAll({ is_active: true }).catch(() => []),
          uomAPI.getAll({ is_active: true }).catch(() => []),
        ]);
        setSuppliers(s);
        setProducts(p);
        setWarehouses(w);
        setUoms(Object.fromEntries(u.map((item) => [item.id, item])));
      } catch (err) {
        setLoadError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selected = products.find((p) => String(p.id) === String(pickProduct));

  const uomChoices = useMemo(() => {
    if (!selected) return [];
    const ids = [selected.purchase_uom_id, selected.stock_uom_id, selected.sales_uom_id];
    return [...new Set(ids.filter(Boolean))].map((id) => uoms[id]).filter(Boolean);
  }, [selected, uoms]);

  useEffect(() => {
    if (!selected) {
      setPickUom('');
      setPickPrice('');
      return;
    }
    setPickUom(String(selected.purchase_uom_id ?? selected.stock_uom_id ?? ''));
    setPickPrice(String(selected.price ?? ''));
  }, [selected]);

  const totals = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    for (const item of items) {
      const net = item.quantity * item.unit_price;
      subtotal += net;
      tax += (net * item.tax_rate) / 100;
    }
    return { subtotal, tax, grand: subtotal + tax };
  }, [items]);

  const addItem = () => {
    setError('');
    const product = selected;
    const quantity = Number(pickQty);
    const unitPrice = Number(pickPrice);
    if (!product) return setError('Once bir urun sec.');
    if (!quantity || quantity <= 0) return setError('Miktar sifirdan buyuk olmali.');
    if (Number.isNaN(unitPrice) || unitPrice < 0) return setError('Gecerli bir fiyat gir.');
    if (items.some((i) => i.product_id === product.id)) {
      return setError(`"${product.name}" zaten listede. Once listeden cikar.`);
    }

    const uomId = pickUom ? Number(pickUom) : null;
    setItems([
      ...items,
      {
        product_id: product.id,
        product_name: product.name,
        product_sku: product.sku,
        uom_id: uomId,
        uom_code: uomId ? uoms[uomId]?.code : null,
        quantity,
        unit_price: unitPrice,
        tax_rate: Number(pickTax) || 0,
      },
    ]);
    setPickProduct('');
    setPickQty(1);
  };

  const removeItem = (productId) =>
    setItems(items.filter((i) => i.product_id !== productId));

  const submit = async (event, saveAsDraft) => {
    event.preventDefault();
    setError('');
    if (!supplierId) return setError('Tedarikci secmelisin.');
    if (items.length === 0) return setError('En az bir kalem eklemelisin.');

    setSaving(true);
    try {
      const order = await purchaseOrderAPI.create({
        supplier_id: Number(supplierId),
        order_date: orderDate,
        expected_date: expectedDate || null,
        warehouse_id: warehouseId ? Number(warehouseId) : null,
        note: note || null,
        save_as_draft: saveAsDraft,
        items: items.map((i) => ({
          product_id: i.product_id,
          uom_id: i.uom_id,
          quantity: String(i.quantity),
          unit_price: String(i.unit_price),
          tax_rate: String(i.tax_rate),
        })),
      });
      onCreated(order);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loading label="Tedarikci ve urunler yukleniyor..." />;
  if (loadError) return <ErrorMessage message={loadError} />;

  return (
    <form
      onSubmit={(e) => submit(e, false)}
      data-testid="purchase-order-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5"
    >
      <h3 className="font-medium text-gray-800 mb-3">Yeni satin alma siparisi</h3>
      <ErrorMessage message={error} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Field label="Tedarikci">
          <select
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value)}
            data-testid="po-supplier"
            className={inputClass}
          >
            <option value="">-- Tedarikci sec --</option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Siparis Tarihi">
          <input
            type="date"
            value={orderDate}
            onChange={(e) => setOrderDate(e.target.value)}
            data-testid="po-date"
            className={inputClass}
          />
        </Field>
        <Field label="Beklenen Teslim">
          <input
            type="date"
            value={expectedDate}
            onChange={(e) => setExpectedDate(e.target.value)}
            data-testid="po-expected-date"
            className={inputClass}
          />
        </Field>
        <Field label="Teslim Deposu">
          <select
            value={warehouseId}
            onChange={(e) => setWarehouseId(e.target.value)}
            data-testid="po-warehouse"
            className={inputClass}
          >
            <option value="">Varsayilan depo</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className="border-t border-gray-100 mt-2 pt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Kalem ekle</h4>
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[220px]">
            <select
              value={pickProduct}
              onChange={(e) => setPickProduct(e.target.value)}
              data-testid="po-pick-product"
              className={inputClass}
            >
              <option value="">-- Urun sec --</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.sku})
                </option>
              ))}
            </select>
          </div>
          <input
            type="number"
            min="0"
            step="any"
            value={pickQty}
            onChange={(e) => setPickQty(e.target.value)}
            placeholder="Miktar"
            data-testid="po-pick-qty"
            className={`${inputClass} w-24`}
          />
          {uomChoices.length > 1 && (
            <select
              value={pickUom}
              onChange={(e) => setPickUom(e.target.value)}
              data-testid="po-pick-uom"
              className={`${inputClass} w-28`}
            >
              {uomChoices.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.code}
                </option>
              ))}
            </select>
          )}
          <input
            type="number"
            min="0"
            step="any"
            value={pickPrice}
            onChange={(e) => setPickPrice(e.target.value)}
            placeholder="Birim fiyat"
            data-testid="po-pick-price"
            className={`${inputClass} w-32`}
          />
          <input
            type="number"
            min="0"
            max="100"
            step="any"
            value={pickTax}
            onChange={(e) => setPickTax(e.target.value)}
            placeholder="KDV %"
            data-testid="po-pick-tax"
            className={`${inputClass} w-24`}
          />
          <Button type="button" variant="secondary" onClick={addItem} data-testid="po-add-item">
            Ekle
          </Button>
        </div>
      </div>

      {items.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm" data-testid="po-items-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Urun</th>
                <th className="text-right px-3 py-2 font-medium">Miktar</th>
                <th className="text-right px-3 py-2 font-medium">Birim Fiyat</th>
                <th className="text-right px-3 py-2 font-medium">KDV</th>
                <th className="text-right px-3 py-2 font-medium">Satir Toplami</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr
                  key={i.product_id}
                  className="border-t border-gray-100"
                  data-testid={`po-item-${i.product_id}`}
                >
                  <td className="px-3 py-2">
                    {i.product_name}
                    <span className="text-gray-400 text-xs ml-2 font-mono">
                      {i.product_sku}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    {i.quantity}
                    {i.uom_code && <span className="text-gray-400 ml-1">{i.uom_code}</span>}
                  </td>
                  <td className="px-3 py-2 text-right">{formatMoney(i.unit_price)}</td>
                  <td className="px-3 py-2 text-right text-gray-500">%{i.tax_rate}</td>
                  <td className="px-3 py-2 text-right font-medium">
                    {formatMoney(i.quantity * i.unit_price)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => removeItem(i.product_id)}
                      data-testid={`po-remove-${i.product_id}`}
                      className="text-red-600 hover:underline text-xs"
                    >
                      Cikar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50">
              <tr className="border-t-2 border-gray-200">
                <td colSpan={4} className="px-3 py-1 text-right text-gray-600">
                  Ara toplam
                </td>
                <td className="px-3 py-1 text-right">{formatMoney(totals.subtotal)}</td>
                <td />
              </tr>
              <tr>
                <td colSpan={4} className="px-3 py-1 text-right text-gray-600">
                  KDV
                </td>
                <td className="px-3 py-1 text-right">{formatMoney(totals.tax)}</td>
                <td />
              </tr>
              <tr>
                <td colSpan={4} className="px-3 py-2 text-right font-medium text-gray-700">
                  Genel toplam
                </td>
                <td
                  className="px-3 py-2 text-right font-semibold text-indigo-700"
                  data-testid="po-form-total"
                >
                  {formatMoney(totals.grand)}
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      <Field label="Not">
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          className={inputClass}
        />
      </Field>

      <div className="flex gap-2 mt-4">
        <Button type="submit" disabled={saving} data-testid="po-submit">
          {saving ? 'Kaydediliyor...' : 'Olustur ve Onayla'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={saving}
          onClick={(e) => submit(e, true)}
          data-testid="po-save-draft"
        >
          Taslak Kaydet
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Vazgec
        </Button>
      </div>
    </form>
  );
}
