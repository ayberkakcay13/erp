import { useState } from 'react';
import { supplierAPI } from '../services/api';
import { Button, ErrorMessage, Field, inputClass } from './ui';

export default function SupplierForm({ supplier, onSaved, onCancel }) {
  const isEdit = Boolean(supplier);
  const [form, setForm] = useState({
    code: supplier?.code ?? '',
    name: supplier?.name ?? '',
    tax_number: supplier?.tax_number ?? '',
    tax_office: supplier?.tax_office ?? '',
    phone: supplier?.phone ?? '',
    email: supplier?.email ?? '',
    city: supplier?.city ?? '',
    address: supplier?.address ?? '',
    contact_person: supplier?.contact_person ?? '',
    payment_term_days: supplier?.payment_term_days ?? 0,
    is_active: supplier?.is_active ?? true,
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const change = (e) => {
    const { name, value, type, checked } = e.target;
    setForm({ ...form, [name]: type === 'checkbox' ? checked : value });
  };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const payload = {
        ...form,
        payment_term_days: Number(form.payment_term_days) || 0,
        tax_number: form.tax_number || null,
        tax_office: form.tax_office || null,
        phone: form.phone || null,
        email: form.email || null,
        city: form.city || null,
        address: form.address || null,
        contact_person: form.contact_person || null,
      };
      const saved = isEdit
        ? await supplierAPI.update(supplier.id, payload)
        : await supplierAPI.create(payload);
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
      data-testid="supplier-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5 max-w-3xl"
    >
      <h3 className="font-medium text-gray-800 mb-3">
        {isEdit ? `Tedarikciyi duzenle: ${supplier.name}` : 'Yeni tedarikci'}
      </h3>
      <ErrorMessage message={error} />

      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Kod">
          <input
            name="code"
            value={form.code}
            onChange={change}
            required
            data-testid="supplier-code"
            className={inputClass}
          />
        </Field>
        <Field label="Unvan">
          <input
            name="name"
            value={form.name}
            onChange={change}
            required
            data-testid="supplier-name"
            className={inputClass}
          />
        </Field>
        <Field label="VKN / TCKN">
          <input
            name="tax_number"
            value={form.tax_number}
            onChange={change}
            inputMode="numeric"
            maxLength={11}
            placeholder="10 veya 11 hane"
            data-testid="supplier-tax-number"
            className={inputClass}
          />
        </Field>
        <Field label="Vergi Dairesi">
          <input
            name="tax_office"
            value={form.tax_office}
            onChange={change}
            className={inputClass}
          />
        </Field>
        <Field label="Telefon">
          <input name="phone" value={form.phone} onChange={change} className={inputClass} />
        </Field>
        <Field label="E-posta">
          <input
            name="email"
            type="email"
            value={form.email}
            onChange={change}
            className={inputClass}
          />
        </Field>
        <Field label="Sehir">
          <input name="city" value={form.city} onChange={change} className={inputClass} />
        </Field>
        <Field label="Yetkili Kisi">
          <input
            name="contact_person"
            value={form.contact_person}
            onChange={change}
            className={inputClass}
          />
        </Field>
        <Field label="Vade (gun)">
          <input
            name="payment_term_days"
            type="number"
            min="0"
            max="365"
            value={form.payment_term_days}
            onChange={change}
            data-testid="supplier-payment-term"
            className={inputClass}
          />
        </Field>
        <Field label="Durum">
          <label className="flex items-center gap-2 text-sm text-gray-700 py-2">
            <input
              name="is_active"
              type="checkbox"
              checked={form.is_active}
              onChange={change}
            />
            Aktif
          </label>
        </Field>
      </div>

      <Field label="Adres">
        <textarea
          name="address"
          value={form.address}
          onChange={change}
          rows={2}
          className={inputClass}
        />
      </Field>

      <div className="flex gap-2 mt-4">
        <Button type="submit" disabled={saving} data-testid="supplier-submit">
          {saving ? 'Kaydediliyor...' : 'Kaydet'}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Vazgec
        </Button>
      </div>
    </form>
  );
}
