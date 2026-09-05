import { useState } from 'react';
import { productAPI } from '../services/api';
import { Button, ErrorMessage, Field, inputClass } from './ui';

export default function ProductForm({ product, onSaved, onCancel }) {
  const isEdit = Boolean(product);
  const [form, setForm] = useState({
    name: product?.name ?? '',
    sku: product?.sku ?? '',
    price: product?.price ?? '',
    stock: product?.stock ?? 0,
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const change = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        sku: form.sku,
        price: Number(form.price),
        stock: Number(form.stock),
      };
      const saved = isEdit
        ? await productAPI.update(product.id, payload)
        : await productAPI.create(payload);
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
      data-testid="product-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5 max-w-lg"
    >
      <h3 className="font-medium text-gray-800 mb-3">
        {isEdit ? `Urunu duzenle: ${product.name}` : 'Yeni urun'}
      </h3>
      <ErrorMessage message={error} />
      <Field label="Urun Adi">
        <input
          name="name"
          value={form.name}
          onChange={change}
          required
          data-testid="product-name"
          className={inputClass}
        />
      </Field>
      <Field label="SKU (stok kodu)">
        <input
          name="sku"
          value={form.sku}
          onChange={change}
          required
          data-testid="product-sku"
          className={inputClass}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Fiyat (TL)">
          <input
            name="price"
            type="number"
            step="0.01"
            min="0"
            value={form.price}
            onChange={change}
            required
            data-testid="product-price"
            className={inputClass}
          />
        </Field>
        <Field label="Stok">
          <input
            name="stock"
            type="number"
            min="0"
            value={form.stock}
            onChange={change}
            required
            data-testid="product-stock"
            className={inputClass}
          />
        </Field>
      </div>
      <div className="flex gap-2 mt-2">
        <Button type="submit" disabled={saving} data-testid="product-submit">
          {saving ? 'Kaydediliyor...' : isEdit ? 'Guncelle' : 'Kaydet'}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Vazgec
        </Button>
      </div>
    </form>
  );
}
