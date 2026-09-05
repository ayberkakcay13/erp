import { useState } from 'react';
import { customerAPI } from '../services/api';
import { Button, ErrorMessage, Field, inputClass } from './ui';

/**
 * customer prop verilirse duzenleme, verilmezse yeni kayit modunda calisir.
 */
export default function CustomerForm({ customer, onSaved, onCancel }) {
  const isEdit = Boolean(customer);
  const [form, setForm] = useState({
    name: customer?.name ?? '',
    email: customer?.email ?? '',
    phone: customer?.phone ?? '',
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const change = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const payload = { ...form, phone: form.phone || null };
      const saved = isEdit
        ? await customerAPI.update(customer.id, payload)
        : await customerAPI.create(payload);
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
      data-testid="customer-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5 max-w-lg"
    >
      <h3 className="font-medium text-gray-800 mb-3">
        {isEdit ? `Musteriyi duzenle: ${customer.name}` : 'Yeni musteri'}
      </h3>
      <ErrorMessage message={error} />
      <Field label="Ad Soyad">
        <input
          name="name"
          value={form.name}
          onChange={change}
          required
          data-testid="customer-name"
          className={inputClass}
        />
      </Field>
      <Field label="E-posta">
        <input
          name="email"
          type="email"
          value={form.email}
          onChange={change}
          required
          data-testid="customer-email"
          className={inputClass}
        />
      </Field>
      <Field label="Telefon">
        <input
          name="phone"
          value={form.phone}
          onChange={change}
          data-testid="customer-phone"
          className={inputClass}
        />
      </Field>
      <div className="flex gap-2 mt-4">
        <Button type="submit" disabled={saving} data-testid="customer-submit">
          {saving ? 'Kaydediliyor...' : isEdit ? 'Guncelle' : 'Kaydet'}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Vazgec
        </Button>
      </div>
    </form>
  );
}
