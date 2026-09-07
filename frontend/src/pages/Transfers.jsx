import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  EmptyState,
  ErrorMessage,
  Field,
  Loading,
  PageHeader,
  formatDate,
  formatQty,
  inputClass,
} from '../components/ui';
import { productAPI, transferAPI, warehouseAPI } from '../services/api';

const emptyItem = () => ({ product_id: '', quantity: '' });

/** Depolar arasi transfer formu. Kaydedilince iki ledger satiri olusur. */
function TransferForm({ warehouses, products, onSaved, onCancel }) {
  const [fromId, setFromId] = useState('');
  const [toId, setToId] = useState('');
  const [note, setNote] = useState('');
  const [items, setItems] = useState([emptyItem()]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const setItem = (index, patch) =>
    setItems(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));

  const submit = async (event) => {
    event.preventDefault();
    setError('');

    const filled = items.filter((i) => i.product_id && Number(i.quantity) > 0);
    if (!fromId || !toId) return setError('Cikis ve giris deposu secilmeli.');
    if (fromId === toId) return setError('Cikis ve giris deposu ayni olamaz.');
    if (filled.length === 0) return setError('En az bir urun ve miktar girilmeli.');

    setSaving(true);
    try {
      const saved = await transferAPI.create({
        from_warehouse_id: Number(fromId),
        to_warehouse_id: Number(toId),
        note: note || null,
        items: filled.map((i) => ({
          product_id: Number(i.product_id),
          quantity: String(i.quantity),
        })),
      });
      onSaved(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="bg-white border border-gray-200 rounded p-4 mb-4"
      data-testid="transfer-form"
    >
      <ErrorMessage message={error} />
      <div className="grid sm:grid-cols-3 gap-3">
        <Field label="Cikis deposu">
          <select
            className={inputClass}
            value={fromId}
            onChange={(e) => setFromId(e.target.value)}
            data-testid="transfer-from"
          >
            <option value="">Seciniz</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Giris deposu">
          <select
            className={inputClass}
            value={toId}
            onChange={(e) => setToId(e.target.value)}
            data-testid="transfer-to"
          >
            <option value="">Seciniz</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Not">
          <input
            className={inputClass}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            data-testid="transfer-note"
          />
        </Field>
      </div>

      <div className="mt-3">
        <div className="text-sm font-medium text-gray-700 mb-2">Urunler</div>
        {items.map((item, index) => (
          <div key={index} className="flex gap-2 mb-2">
            <select
              className={`${inputClass} flex-1`}
              value={item.product_id}
              onChange={(e) => setItem(index, { product_id: e.target.value })}
              data-testid={`transfer-product-${index}`}
            >
              <option value="">Urun seciniz</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.sku})
                </option>
              ))}
            </select>
            <input
              type="number"
              min="0"
              step="any"
              className={`${inputClass} w-32`}
              placeholder="Miktar"
              value={item.quantity}
              onChange={(e) => setItem(index, { quantity: e.target.value })}
              data-testid={`transfer-qty-${index}`}
            />
            {items.length > 1 && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => setItems(items.filter((_, i) => i !== index))}
              >
                Sil
              </Button>
            )}
          </div>
        ))}
        <Button
          type="button"
          variant="secondary"
          onClick={() => setItems([...items, emptyItem()])}
          data-testid="transfer-add-item"
        >
          + Satir Ekle
        </Button>
      </div>

      <div className="mt-4 flex gap-2 justify-end">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Vazgec
        </Button>
        <Button type="submit" disabled={saving} data-testid="transfer-submit">
          {saving ? 'Kaydediliyor...' : 'Transferi Kaydet'}
        </Button>
      </div>
    </form>
  );
}

export default function Transfers() {
  const [transfers, setTransfers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [products, setProducts] = useState([]);
  const [formOpen, setFormOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [list, wh, prods] = await Promise.all([
        transferAPI.getAll(),
        warehouseAPI.getAll({ is_active: true }),
        productAPI.getAll({ limit: 500 }),
      ]);
      setTransfers(list);
      setWarehouses(wh);
      setProducts(prods);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div data-testid="page-Transfers">
      <PageHeader title="Depo Transferleri">
        <Button onClick={() => setFormOpen(true)} data-testid="new-transfer">
          + Yeni Transfer
        </Button>
      </PageHeader>

      <ErrorMessage message={error} onRetry={load} />
      {notice && (
        <div
          data-testid="notice"
          className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-4"
        >
          {notice}
        </div>
      )}

      {formOpen && (
        <TransferForm
          warehouses={warehouses}
          products={products}
          onCancel={() => setFormOpen(false)}
          onSaved={(saved) => {
            setFormOpen(false);
            setNotice(`${saved.transfer_no} olusturuldu.`);
            load();
          }}
        />
      )}

      {loading ? (
        <Loading />
      ) : transfers.length === 0 ? (
        <EmptyState message="Henuz transfer yok." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="transfers-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Transfer No</th>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-left px-4 py-2 font-medium">Cikis</th>
                <th className="text-left px-4 py-2 font-medium">Giris</th>
                <th className="text-left px-4 py-2 font-medium">Urunler</th>
              </tr>
            </thead>
            <tbody>
              {transfers.map((t) => (
                <tr
                  key={t.id}
                  className="border-t border-gray-100"
                  data-testid={`transfer-row-${t.id}`}
                >
                  <td className="px-4 py-2 font-mono text-xs text-gray-700">
                    {t.transfer_no}
                  </td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(t.transfer_date)}</td>
                  <td className="px-4 py-2 text-gray-800">{t.from_warehouse_name}</td>
                  <td className="px-4 py-2 text-gray-800">{t.to_warehouse_name}</td>
                  <td className="px-4 py-2 text-gray-600 text-xs">
                    {t.items
                      .map((i) => `${i.product_name} × ${formatQty(i.quantity)}`)
                      .join(', ')}
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
