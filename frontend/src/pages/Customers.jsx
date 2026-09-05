import { useCallback, useEffect, useState } from 'react';
import CustomerForm from '../components/CustomerForm';
import {
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
} from '../components/ui';
import { customerAPI } from '../services/api';

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setCustomers(await customerAPI.getAll());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (customer) => {
    setEditing(customer);
    setFormOpen(true);
  };

  const handleSaved = (saved) => {
    setFormOpen(false);
    setEditing(null);
    setNotice(`"${saved.name}" kaydedildi.`);
    load();
  };

  const remove = async (customer) => {
    if (!window.confirm(`"${customer.name}" silinsin mi?`)) return;
    setError('');
    try {
      await customerAPI.delete(customer.id);
      setNotice(`"${customer.name}" silindi.`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div data-testid="page-Customers">
      <PageHeader title="Musteriler">
        <Button onClick={openCreate} data-testid="new-customer">
          + Yeni Musteri
        </Button>
      </PageHeader>

      <ErrorMessage message={error} onRetry={load} />
      {notice && (
        <div data-testid="notice" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-4">
          {notice}
        </div>
      )}

      {formOpen && (
        <CustomerForm
          customer={editing}
          onSaved={handleSaved}
          onCancel={() => {
            setFormOpen(false);
            setEditing(null);
          }}
        />
      )}

      {loading ? (
        <Loading />
      ) : customers.length === 0 ? (
        <EmptyState message="Henuz musteri yok. Yukaridaki butonla ekleyebilirsin." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="customers-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Ad Soyad</th>
                <th className="text-left px-4 py-2 font-medium">E-posta</th>
                <th className="text-left px-4 py-2 font-medium">Telefon</th>
                <th className="text-left px-4 py-2 font-medium">Kayit Tarihi</th>
                <th className="text-right px-4 py-2 font-medium">Islemler</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.id} data-testid={`customer-row-${c.id}`} className="border-t border-gray-100">
                  <td className="px-4 py-2 text-gray-800">{c.name}</td>
                  <td className="px-4 py-2 text-gray-600">{c.email}</td>
                  <td className="px-4 py-2 text-gray-600">{c.phone || '-'}</td>
                  <td className="px-4 py-2 text-gray-500">{formatDate(c.created_at)}</td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <Button
                      variant="secondary"
                      onClick={() => openEdit(c)}
                      data-testid={`edit-${c.id}`}
                      className="mr-2"
                    >
                      Duzenle
                    </Button>
                    <Button variant="danger" onClick={() => remove(c)} data-testid={`delete-${c.id}`}>
                      Sil
                    </Button>
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
