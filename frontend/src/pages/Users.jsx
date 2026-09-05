import { useCallback, useEffect, useState } from 'react';
import {
  Badge,
  Button,
  ErrorMessage,
  Field,
  Loading,
  PageHeader,
  formatDate,
  inputClass,
} from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { userAPI } from '../services/api';

function UserForm({ onSaved, onCancel }) {
  const [form, setForm] = useState({
    email: '',
    full_name: '',
    password: '',
    role: 'sales',
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const change = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      onSaved(await userAPI.create({ ...form, full_name: form.full_name || null }));
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      data-testid="user-form"
      className="bg-white border border-gray-200 rounded p-4 mb-5 max-w-lg"
    >
      <h3 className="font-medium text-gray-800 mb-3">Yeni kullanici</h3>
      <ErrorMessage message={error} />
      <Field label="Ad Soyad">
        <input
          name="full_name"
          value={form.full_name}
          onChange={change}
          data-testid="user-fullname"
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
          data-testid="user-email"
          className={inputClass}
        />
      </Field>
      <Field label="Sifre (en az 6 karakter)">
        <input
          name="password"
          type="password"
          value={form.password}
          onChange={change}
          required
          minLength={6}
          data-testid="user-password"
          className={inputClass}
        />
      </Field>
      <Field label="Rol">
        <select
          name="role"
          value={form.role}
          onChange={change}
          data-testid="user-role"
          className={inputClass}
        >
          <option value="sales">Satis Elemani (sales)</option>
          <option value="admin">Yonetici (admin)</option>
        </select>
      </Field>
      <div className="flex gap-2 mt-4">
        <Button type="submit" disabled={saving} data-testid="user-submit">
          {saving ? 'Kaydediliyor...' : 'Kaydet'}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Vazgec
        </Button>
      </div>
    </form>
  );
}

export default function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const { user: me } = useAuth();

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setUsers(await userAPI.getAll());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleActive = async (u) => {
    setError('');
    try {
      await (u.is_active ? userAPI.deactivate(u.id) : userAPI.activate(u.id));
      setNotice(`${u.email} ${u.is_active ? 'devre disi birakildi' : 'tekrar aktif edildi'}.`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div data-testid="page-Users">
      <PageHeader title="Kullanicilar">
        <Button onClick={() => setFormOpen(true)} data-testid="new-user">
          + Yeni Kullanici
        </Button>
      </PageHeader>

      <ErrorMessage message={error} onRetry={load} />
      {notice && (
        <div data-testid="notice" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-4">
          {notice}
        </div>
      )}

      {formOpen && (
        <UserForm
          onSaved={(created) => {
            setFormOpen(false);
            setNotice(`"${created.email}" olusturuldu (${created.role}).`);
            load();
          }}
          onCancel={() => setFormOpen(false)}
        />
      )}

      {loading ? (
        <Loading />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="users-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Ad Soyad</th>
                <th className="text-left px-4 py-2 font-medium">E-posta</th>
                <th className="text-left px-4 py-2 font-medium">Rol</th>
                <th className="text-left px-4 py-2 font-medium">Durum</th>
                <th className="text-left px-4 py-2 font-medium">Kayit</th>
                <th className="text-right px-4 py-2 font-medium">Islem</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} data-testid={`user-row-${u.id}`} className="border-t border-gray-100">
                  <td className="px-4 py-2 text-gray-800">
                    {u.full_name || '-'}
                    {u.id === me?.id && (
                      <span className="ml-2 text-xs text-indigo-600">(sen)</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-gray-600">{u.email}</td>
                  <td className="px-4 py-2">
                    <Badge tone={u.role === 'admin' ? 'blue' : 'gray'}>{u.role}</Badge>
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={u.is_active ? 'green' : 'red'}>
                      {u.is_active ? 'Aktif' : 'Pasif'}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-gray-500">{formatDate(u.created_at)}</td>
                  <td className="px-4 py-2 text-right">
                    {u.id !== me?.id && (
                      <Button
                        variant={u.is_active ? 'danger' : 'secondary'}
                        onClick={() => toggleActive(u)}
                        data-testid={`toggle-${u.id}`}
                      >
                        {u.is_active ? 'Devre disi birak' : 'Aktif et'}
                      </Button>
                    )}
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
