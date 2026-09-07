import { useCallback, useEffect, useState } from 'react';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Field,
  Loading,
  PageHeader,
  formatDate,
  inputClass,
} from '../components/ui';
import { tenantAPI } from '../services/api';

const MODULE_LABELS = {
  sales: 'Satis',
  purchase: 'Satin Alma',
  stock: 'Stok',
  invoice: 'Fatura',
  reports: 'Raporlar',
  manufacturing: 'Uretim',
  payroll: 'Bordro',
  accounting: 'Muhasebe',
  efatura: 'e-Fatura',
};

const ALL_MODULES = Object.keys(MODULE_LABELS);

const planTone = { free: 'gray', basic: 'blue', pro: 'green' };

function NewTenantForm({ onCreated, onCancel }) {
  const [form, setForm] = useState({
    name: '', slug: '', tax_number: '', plan: 'free',
    admin_email: '', admin_password: '', admin_full_name: '',
  });
  const [modules, setModules] = useState(['sales', 'stock', 'invoice', 'reports']);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const set = (patch) => setForm({ ...form, ...patch });

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setSaving(true);
    try {
      const payload = { ...form, modules };
      // Bos alanlar gonderilmesin: backend null bekliyor
      for (const key of ['tax_number', 'admin_email', 'admin_password', 'admin_full_name']) {
        if (!payload[key]) delete payload[key];
      }
      onCreated(await tenantAPI.create(payload));
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
      data-testid="tenant-form"
    >
      <ErrorMessage message={error} />
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Field label="Firma adi">
          <input
            className={inputClass}
            value={form.name}
            onChange={(e) => set({ name: e.target.value })}
            required
            data-testid="tenant-name"
          />
        </Field>
        <Field label="Kisa ad (subdomain)">
          <input
            className={inputClass}
            value={form.slug}
            onChange={(e) => set({ slug: e.target.value.toLowerCase() })}
            placeholder="ornek-firma"
            pattern="[a-z0-9][a-z0-9-]*"
            required
            data-testid="tenant-slug"
          />
        </Field>
        <Field label="VKN">
          <input
            className={inputClass}
            value={form.tax_number}
            onChange={(e) => set({ tax_number: e.target.value })}
            data-testid="tenant-tax"
          />
        </Field>
        <Field label="Plan">
          <select
            className={inputClass}
            value={form.plan}
            onChange={(e) => set({ plan: e.target.value })}
            data-testid="tenant-plan"
          >
            <option value="free">Free</option>
            <option value="basic">Basic</option>
            <option value="pro">Pro</option>
          </select>
        </Field>
      </div>

      <div className="mt-3">
        <div className="text-sm font-medium text-gray-700 mb-2">Acik moduller</div>
        <div className="flex flex-wrap gap-3">
          {ALL_MODULES.map((code) => (
            <label key={code} className="flex items-center gap-1.5 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={modules.includes(code)}
                onChange={(e) =>
                  setModules(
                    e.target.checked
                      ? [...modules, code]
                      : modules.filter((m) => m !== code)
                  )
                }
                data-testid={`new-module-${code}`}
              />
              {MODULE_LABELS[code]}
            </label>
          ))}
        </div>
      </div>

      <div className="mt-3">
        <div className="text-sm font-medium text-gray-700 mb-2">
          Firma yoneticisi (opsiyonel)
        </div>
        <div className="grid sm:grid-cols-3 gap-3">
          <Field label="E-posta">
            <input
              type="email"
              className={inputClass}
              value={form.admin_email}
              onChange={(e) => set({ admin_email: e.target.value })}
              data-testid="tenant-admin-email"
            />
          </Field>
          <Field label="Sifre">
            <input
              type="password"
              className={inputClass}
              value={form.admin_password}
              onChange={(e) => set({ admin_password: e.target.value })}
              minLength={6}
              data-testid="tenant-admin-password"
            />
          </Field>
          <Field label="Ad soyad">
            <input
              className={inputClass}
              value={form.admin_full_name}
              onChange={(e) => set({ admin_full_name: e.target.value })}
              data-testid="tenant-admin-name"
            />
          </Field>
        </div>
      </div>

      <div className="mt-4 flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Vazgec
        </Button>
        <Button type="submit" disabled={saving} data-testid="tenant-submit">
          {saving ? 'Olusturuluyor...' : 'Firmayi Olustur'}
        </Button>
      </div>
    </form>
  );
}

/** Platform sahibinin firma yonetim ekrani (Phase 12). */
export default function Tenants() {
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setTenants(await tenantAPI.getAll());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleModule = async (tenant, code) => {
    setBusyId(tenant.id);
    setError('');
    const enabled = tenant.modules.filter((m) => m.is_enabled).map((m) => m.module_code);
    const next = enabled.includes(code)
      ? enabled.filter((m) => m !== code)
      : [...enabled, code];
    try {
      const modules = await tenantAPI.setModules(tenant.id, next);
      setTenants((list) =>
        list.map((t) => (t.id === tenant.id ? { ...t, modules } : t))
      );
      setNotice(`${tenant.name}: "${MODULE_LABELS[code]}" modulu guncellendi.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div data-testid="page-Tenants">
      <PageHeader title="Firmalar">
        <Button onClick={() => setFormOpen(true)} data-testid="new-tenant">
          + Yeni Firma
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
        <NewTenantForm
          onCancel={() => setFormOpen(false)}
          onCreated={(created) => {
            setFormOpen(false);
            setNotice(`"${created.name}" olusturuldu.`);
            load();
          }}
        />
      )}

      {loading ? (
        <Loading />
      ) : tenants.length === 0 ? (
        <EmptyState message="Henuz firma yok." />
      ) : (
        <div className="space-y-3">
          {tenants.map((tenant) => {
            const enabled = new Set(
              tenant.modules.filter((m) => m.is_enabled).map((m) => m.module_code)
            );
            return (
              <div
                key={tenant.id}
                className="bg-white border border-gray-200 rounded p-4"
                data-testid={`tenant-row-${tenant.id}`}
              >
                <div className="flex flex-wrap items-center gap-3 mb-3">
                  <span className="font-medium text-gray-800">{tenant.name}</span>
                  <span className="font-mono text-xs text-gray-500">{tenant.slug}</span>
                  <Badge tone={planTone[tenant.plan] ?? 'gray'}>{tenant.plan}</Badge>
                  {!tenant.is_active && <Badge tone="red">Pasif</Badge>}
                  <span className="text-xs text-gray-400 ml-auto">
                    {formatDate(tenant.created_at)}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {ALL_MODULES.map((code) => (
                    <button
                      key={code}
                      type="button"
                      disabled={busyId === tenant.id}
                      onClick={() => toggleModule(tenant, code)}
                      data-testid={`module-${tenant.id}-${code}`}
                      className={`text-xs px-2 py-1 rounded border transition-colors ${
                        enabled.has(code)
                          ? 'bg-green-50 border-green-300 text-green-800'
                          : 'bg-gray-50 border-gray-200 text-gray-400'
                      }`}
                    >
                      {MODULE_LABELS[code]}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
