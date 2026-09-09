import { useEffect, useState } from 'react';
import {
  brandAPI,
  itemGroupAPI,
  productAPI,
  uomAPI,
} from '../services/api';
import { Button, ErrorMessage, Field, inputClass } from './ui';

const PRODUCT_TYPES = [
  { value: 'stoklu', label: 'Stoklu' },
  { value: 'hizmet', label: 'Hizmet (stok tutmaz)' },
  { value: 'sarf', label: 'Sarf' },
];

/** Kategori agacini "Elektronik > Bilgisayar" seklinde duz listeye acar. */
function flattenTree(nodes, prefix = '') {
  const rows = [];
  for (const node of nodes) {
    const label = prefix ? `${prefix} > ${node.name}` : node.name;
    rows.push({ id: node.id, label });
    rows.push(...flattenTree(node.children ?? [], label));
  }
  return rows;
}

export default function ProductForm({ product, onSaved, onCancel }) {
  const isEdit = Boolean(product);
  const [form, setForm] = useState({
    name: product?.name ?? '',
    sku: product?.sku ?? '',
    price: product?.price ?? '',
    stock: product?.stock ?? 0,
    // Phase 13 alanlari
    stock_uom_id: product?.stock_uom_id ?? '',
    purchase_uom_id: product?.purchase_uom_id ?? '',
    sales_uom_id: product?.sales_uom_id ?? '',
    item_group_id: product?.item_group_id ?? '',
    brand_id: product?.brand_id ?? '',
    product_type: product?.product_type ?? 'stoklu',
    description: product?.description ?? '',
    is_variant_template: product?.is_variant_template ?? false,
  });
  const [barcode, setBarcode] = useState('');
  const [uoms, setUoms] = useState([]);
  const [groups, setGroups] = useState([]);
  const [brands, setBrands] = useState([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([uomAPI.getAll(), itemGroupAPI.tree(), brandAPI.getAll()])
      .then(([u, tree, b]) => {
        setUoms(u);
        setGroups(flattenTree(tree));
        setBrands(b);
      })
      .catch((err) => setError(err.message));
  }, []);

  const change = (e) => {
    const { name, type, checked, value } = e.target;
    setForm({ ...form, [name]: type === 'checkbox' ? checked : value });
  };

  // Sablon ve hizmet urunu stok tutmaz; stok alanini kapatiyoruz
  const stockDisabled = form.is_variant_template || form.product_type === 'hizmet';

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const optional = (value) => (value === '' ? null : Number(value));
      const payload = {
        name: form.name,
        sku: form.sku,
        price: String(form.price),
        stock: stockDisabled ? '0' : String(form.stock),
        stock_uom_id: optional(form.stock_uom_id),
        purchase_uom_id: optional(form.purchase_uom_id),
        sales_uom_id: optional(form.sales_uom_id),
        item_group_id: optional(form.item_group_id),
        brand_id: optional(form.brand_id),
        product_type: form.product_type,
        description: form.description || null,
        is_variant_template: form.is_variant_template,
      };
      if (!isEdit && barcode.trim()) {
        payload.barcodes = [{ barcode: barcode.trim(), barcode_type: 'EAN13' }];
      }
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

  const uomOptions = (testid, name) => (
    <select
      name={name}
      value={form[name]}
      onChange={change}
      data-testid={testid}
      className={inputClass}
    >
      <option value="">-</option>
      {uoms.map((u) => (
        <option key={u.id} value={u.id}>
          {u.name}
        </option>
      ))}
    </select>
  );

  return (
    <form
      onSubmit={submit}
      data-testid="product-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5 max-w-3xl"
    >
      <h3 className="font-medium text-gray-800 mb-3">
        {isEdit ? `Urunu duzenle: ${product.name}` : 'Yeni urun'}
      </h3>
      <ErrorMessage message={error} />

      <div className="grid sm:grid-cols-2 gap-3">
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
      </div>

      <div className="grid sm:grid-cols-3 gap-3">
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
        <Field label="Tip">
          <select
            name="product_type"
            value={form.product_type}
            onChange={change}
            data-testid="product-type"
            className={inputClass}
          >
            {PRODUCT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label={stockDisabled ? 'Stok (bu tipte tutulmaz)' : 'Stok'}>
          <input
            name="stock"
            type="number"
            min="0"
            step="any"
            value={stockDisabled ? 0 : form.stock}
            onChange={change}
            disabled={stockDisabled}
            data-testid="product-stock"
            className={inputClass}
          />
        </Field>
      </div>

      <div className="grid sm:grid-cols-3 gap-3">
        <Field label="Stok birimi">{uomOptions('product-stock-uom', 'stock_uom_id')}</Field>
        <Field label="Alis birimi">
          {uomOptions('product-purchase-uom', 'purchase_uom_id')}
        </Field>
        <Field label="Satis birimi">
          {uomOptions('product-sales-uom', 'sales_uom_id')}
        </Field>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Kategori">
          <select
            name="item_group_id"
            value={form.item_group_id}
            onChange={change}
            data-testid="product-group"
            className={inputClass}
          >
            <option value="">-</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Marka">
          <select
            name="brand_id"
            value={form.brand_id}
            onChange={change}
            data-testid="product-brand"
            className={inputClass}
          >
            <option value="">-</option>
            {brands.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {!isEdit && (
        <Field label="Barkod (opsiyonel, EAN13)">
          <input
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
            data-testid="product-barcode"
            className={inputClass}
            placeholder="8690000000000"
          />
        </Field>
      )}

      <Field label="Aciklama">
        <textarea
          name="description"
          value={form.description}
          onChange={change}
          rows={2}
          data-testid="product-description"
          className={inputClass}
        />
      </Field>

      <label className="flex items-center gap-2 text-sm text-gray-700 mb-3">
        <input
          type="checkbox"
          name="is_variant_template"
          checked={form.is_variant_template}
          onChange={change}
          data-testid="product-is-template"
        />
        Varyant sablonu (stok varyantlarda tutulur, sablonda tutulmaz)
      </label>

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
