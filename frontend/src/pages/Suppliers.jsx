import { useCallback, useEffect, useMemo, useState } from 'react';
import FilterBar, { FilterField, SearchInput, SortableTh } from '../components/FilterBar';
import SupplierForm from '../components/SupplierForm';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
} from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { supplierAPI } from '../services/api';
import { matches, sortRows, toggleSort } from '../utils/filters';

export default function Suppliers() {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [notice, setNotice] = useState('');
  const { isAdmin } = useAuth();

  const [search, setSearch] = useState('');
  const [sort, setSort] = useState({ key: null, dir: 'asc' });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setSuppliers(await supplierAPI.getAll());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    const filtered = suppliers.filter(
      (s) => matches(s, ['code', 'name', 'tax_number', 'city', 'contact_person'], search)
    );
    return sortRows(filtered, sort, ['payment_term_days', 'id']);
  }, [suppliers, search, sort]);

  const hasFilters = search.trim() !== '' || Boolean(sort.key);

  const handleSaved = (saved) => {
    setFormOpen(false);
    setEditing(null);
    setNotice(`"${saved.name}" kaydedildi.`);
    load();
  };

  const remove = async (supplier) => {
    if (!window.confirm(`"${supplier.name}" silinsin mi?`)) return;
    setError('');
    try {
      await supplierAPI.delete(supplier.id);
      setNotice(`"${supplier.name}" silindi.`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const onSort = (k) => setSort(toggleSort(sort, k));

  return (
    <div data-testid="page-Suppliers">
      <PageHeader title="Tedarikciler">
        <Button
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
          data-testid="new-supplier"
        >
          + Yeni Tedarikci
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
        <SupplierForm
          supplier={editing}
          onSaved={handleSaved}
          onCancel={() => {
            setFormOpen(false);
            setEditing(null);
          }}
        />
      )}

      {!loading && (
        <FilterBar
          resultCount={visible.length}
          totalCount={suppliers.length}
          hasFilters={hasFilters}
          onClear={() => {
            setSearch('');
            setSort({ key: null, dir: 'asc' });
          }}
        >
          <FilterField label="Ara">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Unvan, kod, VKN veya sehir"
              testid="supplier-search"
            />
          </FilterField>
        </FilterBar>
      )}

      {loading ? (
        <Loading />
      ) : suppliers.length === 0 ? (
        <EmptyState message="Henuz tedarikci yok." />
      ) : visible.length === 0 ? (
        <EmptyState message="Arama kriterlerine uyan tedarikci bulunamadi." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="suppliers-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <SortableTh label="Kod" sortKey="code" sort={sort} onSort={onSort} />
                <SortableTh label="Unvan" sortKey="name" sort={sort} onSort={onSort} />
                <th className="text-left px-4 py-2 font-medium">VKN</th>
                <th className="text-left px-4 py-2 font-medium">Yetkili</th>
                <SortableTh
                  label="Vade"
                  sortKey="payment_term_days"
                  sort={sort}
                  onSort={onSort}
                  align="right"
                />
                <th className="text-left px-4 py-2 font-medium">Durum</th>
                <th className="text-right px-4 py-2 font-medium">Islemler</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <tr
                  key={s.id}
                  data-testid={`supplier-row-${s.id}`}
                  className="border-t border-gray-100"
                >
                  <td className="px-4 py-2 font-mono text-xs text-gray-500">{s.code}</td>
                  <td className="px-4 py-2 text-gray-800">
                    {s.name}
                    {s.city && <div className="text-xs text-gray-400">{s.city}</div>}
                  </td>
                  <td className="px-4 py-2 text-gray-600 font-mono text-xs">
                    {s.tax_number || '-'}
                  </td>
                  <td className="px-4 py-2 text-gray-600">{s.contact_person || '-'}</td>
                  <td className="px-4 py-2 text-right text-gray-800">
                    {s.payment_term_days} gun
                  </td>
                  <td className="px-4 py-2">
                    {s.is_active ? (
                      <Badge tone="green">Aktif</Badge>
                    ) : (
                      <Badge tone="gray">Pasif</Badge>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <Button
                      variant="secondary"
                      className="mr-2"
                      onClick={() => {
                        setEditing(s);
                        setFormOpen(true);
                      }}
                      data-testid={`edit-supplier-${s.id}`}
                    >
                      Duzenle
                    </Button>
                    {isAdmin && (
                      <Button
                        variant="danger"
                        onClick={() => remove(s)}
                        data-testid={`delete-supplier-${s.id}`}
                      >
                        Sil
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
