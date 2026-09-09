import { useEffect, useMemo, useState } from 'react';
import {
  productAPI,
  purchaseInvoiceAPI,
  purchaseReceiptAPI,
  supplierAPI,
} from '../services/api';
import {
  Button,
  ErrorMessage,
  Field,
  Loading,
  formatMoney,
  inputClass,
} from './ui';

export default function PurchaseInvoiceForm({ onCreated, onCancel }) {
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [receipts, setReceipts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [supplierId, setSupplierId] = useState('');
  const [receiptId, setReceiptId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().slice(0, 10));
  const [dueDate, setDueDate] = useState('');
  const [note, setNote] = useState('');
  const [items, setItems] = useState([]);

  const [pickProduct, setPickProduct] = useState('');
  const [pickQty, setPickQty] = useState(1);
  const [pickPrice, setPickPrice] = useState('');
  const [pickTax, setPickTax] = useState('20');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [s, p, r] = await Promise.all([
          supplierAPI.getAll({ is_active: true }),
          productAPI.getAll(),
          purchaseReceiptAPI.getAll(),
        ]);
        setSuppliers(s);
        setProducts(p);
        setReceipts(r.filter((receipt) => receipt.docstatus === 1));
      } catch (err) {
        setLoadError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const supplierReceipts = useMemo(
    () =>
      receipts.filter(
        (r) => !supplierId || String(r.supplier_id) === String(supplierId)
      ),
    [receipts, supplierId]
  );

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

  const loadFromReceipt = () => {
    const receipt = receipts.find((r) => String(r.id) === String(receiptId));
    if (!receipt) return setError('Once bir mal kabul sec.');
    setError('');
    setSupplierId(String(receipt.supplier_id));
    setItems(
      receipt.items
        .filter((item) => Number(item.accepted_quantity) > 0)
        .map((item) => ({
          product_id: item.product_id,
          product_name: item.product_name,
          product_sku: item.product_sku,
          uom_id: item.uom_id,
          uom_code: item.uom_code,
          quantity: Number(item.accepted_quantity),
          unit_price: Number(item.unit_price),
          tax_rate: 20,
        }))
    );
  };

  const addItem = () => {
    setError('');
    const product = products.find((p) => String(p.id) === String(pickProduct));
    const quantity = Number(pickQty);
    const unitPrice = Number(pickPrice);
    if (!product) return setError('Once bir urun sec.');
    if (!quantity || quantity <= 0) return setError('Miktar sifirdan buyuk olmali.');
    if (Number.isNaN(unitPrice) || unitPrice < 0) return setError('Gecerli bir fiyat gir.');

    setItems([
      ...items,
      {
        product_id: product.id,
        product_name: product.name,
        product_sku: product.sku,
        uom_id: product.purchase_uom_id ?? product.stock_uom_id ?? null,
        uom_code: null,
        quantity,
        unit_price: unitPrice,
        tax_rate: Number(pickTax) || 0,
      },
    ]);
    setPickProduct('');
    setPickQty(1);
    setPickPrice('');
  };

  const removeItem = (index) => setItems(items.filter((_, i) => i !== index));

  const submit = async (event, saveAsDraft) => {
    event.preventDefault();
    setError('');
    if (!supplierId) return setError('Tedarikci secmelisin.');
    if (!invoiceNumber.trim()) return setError('Tedarikcinin fatura numarasini gir.');
    if (items.length === 0) return setError('En az bir kalem eklemelisin.');

    setSaving(true);
    try {
      const invoice = await purchaseInvoiceAPI.create({
        supplier_id: Number(supplierId),
        invoice_number: invoiceNumber.trim(),
        purchase_receipt_id: receiptId ? Number(receiptId) : null,
        invoice_date: invoiceDate,
        due_date: dueDate || null,
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
      onCreated(invoice);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loading label="Tedarikci ve mal kabuller yukleniyor..." />;
  if (loadError) return <ErrorMessage message={loadError} />;

  return (
    <form
      onSubmit={(e) => submit(e, false)}
      data-testid="purchase-invoice-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5"
    >
      <h3 className="font-medium text-gray-800 mb-3">Yeni alis faturasi</h3>
      <ErrorMessage message={error} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <Field label="Mal Kabul (opsiyonel)">
          <div className="flex gap-2">
            <select
              value={receiptId}
              onChange={(e) => setReceiptId(e.target.value)}
              data-testid="invoice-receipt"
              className={inputClass}
            >
              <option value="">Mal kabulsuz</option>
              {supplierReceipts.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.receipt_number} - {r.supplier_name}
                </option>
              ))}
            </select>
            <Button
              type="button"
              variant="secondary"
              onClick={loadFromReceipt}
              data-testid="invoice-from-receipt"
            >
              Getir
            </Button>
          </div>
        </Field>
        <Field label="Tedarikci">
          <select
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value)}
            data-testid="invoice-supplier"
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
        <Field label="Tedarikci Fatura No">
          <input
            value={invoiceNumber}
            onChange={(e) => setInvoiceNumber(e.target.value)}
            required
            data-testid="invoice-number"
            className={inputClass}
          />
        </Field>
        <Field label="Fatura Tarihi">
          <input
            type="date"
            value={invoiceDate}
            onChange={(e) => setInvoiceDate(e.target.value)}
            data-testid="invoice-date"
            className={inputClass}
          />
        </Field>
        <Field label="Vade Tarihi">
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            placeholder="Bos birakilirsa vadeden hesaplanir"
            data-testid="invoice-due-date"
            className={inputClass}
          />
        </Field>
      </div>

      <div className="border-t border-gray-100 mt-2 pt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Kalem ekle</h4>
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[220px]">
            <select
              value={pickProduct}
              onChange={(e) => setPickProduct(e.target.value)}
              data-testid="invoice-pick-product"
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
            className={`${inputClass} w-24`}
          />
          <input
            type="number"
            min="0"
            step="any"
            value={pickPrice}
            onChange={(e) => setPickPrice(e.target.value)}
            placeholder="Birim fiyat"
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
            className={`${inputClass} w-24`}
          />
          <Button
            type="button"
            variant="secondary"
            onClick={addItem}
            data-testid="invoice-add-item"
          >
            Ekle
          </Button>
        </div>
      </div>

      {items.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm" data-testid="invoice-items-table">
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
              {items.map((item, index) => (
                <tr key={`${item.product_id}-${index}`} className="border-t border-gray-100">
                  <td className="px-3 py-2">
                    {item.product_name}
                    <span className="text-gray-400 text-xs ml-2 font-mono">
                      {item.product_sku}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    {item.quantity}
                    {item.uom_code && <span className="text-gray-400 ml-1">{item.uom_code}</span>}
                  </td>
                  <td className="px-3 py-2 text-right">{formatMoney(item.unit_price)}</td>
                  <td className="px-3 py-2 text-right text-gray-500">%{item.tax_rate}</td>
                  <td className="px-3 py-2 text-right font-medium">
                    {formatMoney(item.quantity * item.unit_price)}
                  </td>
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
                  data-testid="invoice-form-total"
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
        <Button type="submit" disabled={saving} data-testid="invoice-submit">
          {saving ? 'Kaydediliyor...' : 'Olustur ve Onayla'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={saving}
          onClick={(e) => submit(e, true)}
          data-testid="invoice-save-draft"
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
