import { useEffect, useState } from 'react';
import {
  purchaseOrderAPI,
  purchaseReceiptAPI,
  supplierAPI,
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

export default function PurchaseReceiptForm({ onCreated, onCancel }) {
  const [suppliers, setSuppliers] = useState([]);
  const [orders, setOrders] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [supplierId, setSupplierId] = useState('');
  const [orderId, setOrderId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [receiptDate, setReceiptDate] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState('');
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [fetching, setFetching] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [s, o, w] = await Promise.all([
          supplierAPI.getAll({ is_active: true }),
          purchaseOrderAPI.getAll({ status: 'beklemede' }),
          warehouseAPI.getAll({ is_active: true }).catch(() => []),
        ]);
        const partial = await purchaseOrderAPI
          .getAll({ status: 'kismi_teslim' })
          .catch(() => []);
        setSuppliers(s);
        setOrders([...o, ...partial].filter((order) => order.docstatus === 1));
        setWarehouses(w);
      } catch (err) {
        setLoadError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const loadFromOrder = async () => {
    if (!orderId) return setError('Once bir siparis sec.');
    setError('');
    setFetching(true);
    try {
      const draft = await purchaseReceiptAPI.fromOrder(Number(orderId));
      setSupplierId(String(draft.supplier_id));
      if (draft.warehouse_id) setWarehouseId(String(draft.warehouse_id));
      setItems(
        draft.items.map((item) => ({
          purchase_order_item_id: item.purchase_order_item_id,
          product_id: item.product_id,
          product_name: item.product_name,
          product_sku: item.product_sku,
          uom_id: item.uom_id,
          uom_code: item.uom_code,
          quantity: Number(item.quantity),
          accepted_quantity: Number(item.accepted_quantity),
          rejected_quantity: 0,
          unit_price: Number(item.unit_price),
          reject_reason: '',
        }))
      );
      if (draft.items.length === 0) {
        setError('Bu siparisin teslim alinmayi bekleyen kalemi kalmamis.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setFetching(false);
    }
  };

  const updateItem = (index, field, value) => {
    setItems(items.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
  };

  const removeItem = (index) => setItems(items.filter((_, i) => i !== index));

  const submit = async (event, saveAsDraft) => {
    event.preventDefault();
    setError('');
    if (!supplierId) return setError('Tedarikci secmelisin.');
    if (items.length === 0) return setError('En az bir kalem olmali.');

    setSaving(true);
    try {
      const receipt = await purchaseReceiptAPI.create({
        supplier_id: Number(supplierId),
        purchase_order_id: orderId ? Number(orderId) : null,
        warehouse_id: warehouseId ? Number(warehouseId) : null,
        receipt_date: receiptDate,
        note: note || null,
        save_as_draft: saveAsDraft,
        items: items.map((i) => ({
          product_id: i.product_id,
          purchase_order_item_id: i.purchase_order_item_id ?? null,
          uom_id: i.uom_id,
          quantity: String(i.quantity),
          accepted_quantity: String(i.accepted_quantity),
          rejected_quantity: String(i.rejected_quantity || 0),
          unit_price: String(i.unit_price),
          reject_reason: i.reject_reason || null,
        })),
      });
      onCreated(receipt);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loading label="Siparis ve tedarikciler yukleniyor..." />;
  if (loadError) return <ErrorMessage message={loadError} />;

  return (
    <form
      onSubmit={(e) => submit(e, false)}
      data-testid="purchase-receipt-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5"
    >
      <h3 className="font-medium text-gray-800 mb-3">Yeni mal kabul</h3>
      <ErrorMessage message={error} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Field label="Siparis (opsiyonel)">
          <div className="flex gap-2">
            <select
              value={orderId}
              onChange={(e) => setOrderId(e.target.value)}
              data-testid="receipt-order"
              className={inputClass}
            >
              <option value="">Siparissiz kabul</option>
              {orders.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.po_number} - {o.supplier_name}
                </option>
              ))}
            </select>
            <Button
              type="button"
              variant="secondary"
              onClick={loadFromOrder}
              disabled={fetching}
              data-testid="receipt-from-order"
            >
              {fetching ? '...' : 'Siparisten Getir'}
            </Button>
          </div>
        </Field>
        <Field label="Tedarikci">
          <select
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value)}
            data-testid="receipt-supplier"
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
        <Field label="Kabul Tarihi">
          <input
            type="date"
            value={receiptDate}
            onChange={(e) => setReceiptDate(e.target.value)}
            data-testid="receipt-date"
            className={inputClass}
          />
        </Field>
        <Field label="Depo">
          <select
            value={warehouseId}
            onChange={(e) => setWarehouseId(e.target.value)}
            data-testid="receipt-warehouse"
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

      {items.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm" data-testid="receipt-items-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Urun</th>
                <th className="text-right px-3 py-2 font-medium">Gelen</th>
                <th className="text-right px-3 py-2 font-medium">Kabul</th>
                <th className="text-right px-3 py-2 font-medium">Red</th>
                <th className="text-left px-3 py-2 font-medium">Red Sebebi</th>
                <th className="text-right px-3 py-2 font-medium">Birim Fiyat</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr
                  key={`${item.product_id}-${index}`}
                  className="border-t border-gray-100"
                  data-testid={`receipt-item-${item.product_id}`}
                >
                  <td className="px-3 py-2">
                    {item.product_name}
                    <span className="text-gray-400 text-xs ml-2 font-mono">
                      {item.product_sku}
                    </span>
                    {item.uom_code && (
                      <span className="text-gray-400 text-xs ml-2">({item.uom_code})</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={item.quantity}
                      onChange={(e) => updateItem(index, 'quantity', Number(e.target.value))}
                      className={`${inputClass} w-24 text-right`}
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={item.accepted_quantity}
                      onChange={(e) =>
                        updateItem(index, 'accepted_quantity', Number(e.target.value))
                      }
                      data-testid={`receipt-accepted-${item.product_id}`}
                      className={`${inputClass} w-24 text-right`}
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={item.rejected_quantity}
                      onChange={(e) =>
                        updateItem(index, 'rejected_quantity', Number(e.target.value))
                      }
                      className={`${inputClass} w-20 text-right`}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      value={item.reject_reason}
                      onChange={(e) => updateItem(index, 'reject_reason', e.target.value)}
                      placeholder="-"
                      className={`${inputClass} w-40`}
                    />
                  </td>
                  <td className="px-3 py-2 text-right">{formatMoney(item.unit_price)}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => removeItem(index)}
                      className="text-red-600 hover:underline text-xs"
                    >
                      Cikar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
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
        <Button type="submit" disabled={saving} data-testid="receipt-submit">
          {saving ? 'Kaydediliyor...' : 'Kabul Et ve Onayla'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={saving}
          onClick={(e) => submit(e, true)}
          data-testid="receipt-save-draft"
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
