import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import FilterBar, { FilterField, SearchInput, SelectFilter } from '../components/FilterBar';
import SalesForm from '../components/SalesForm';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  formatMoney,
  inputClass,
} from '../components/ui';
import { salesAPI } from '../services/api';
import { inDateRange, matches, sortRows, toggleSort } from '../utils/filters';

export const statusTone = {
  pending: 'yellow',
  completed: 'green',
  cancelled: 'red',
};

export const statusLabel = {
  pending: 'Bekliyor',
  completed: 'Tamamlandi',
  cancelled: 'Iptal',
};

const STATUS_OPTIONS = [
  { value: 'all', label: 'Tum durumlar' },
  { value: 'pending', label: 'Bekliyor' },
  { value: 'completed', label: 'Tamamlandi' },
  { value: 'cancelled', label: 'Iptal' },
];

export default function Sales() {
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const navigate = useNavigate();

  // Phase 8: musteri araması + tarih araligi + durum filtresi
  const [search, setSearch] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState({ key: null, dir: 'asc' });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setSales(await salesAPI.getAll());
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
    const rows = sales
      // Musteri adi nested geldigi icin arama oncesi duz bir alana kopyalaniyor
      .map((s) => ({ ...s, customer_name: s.customer?.name ?? '' }))
      .filter(
        (s) =>
          matches(s, ['customer_name'], search) &&
          inDateRange(s.sale_date, startDate, endDate) &&
          (status === 'all' || s.status === status)
      );
    return sortRows(rows, sort, ['id', 'total_amount']);
  }, [sales, search, startDate, endDate, status, sort]);

  const hasFilters =
    search.trim() !== '' || startDate !== '' || endDate !== '' || status !== 'all' || Boolean(sort.key);

  const clearFilters = () => {
    setSearch('');
    setStartDate('');
    setEndDate('');
    setStatus('all');
    setSort({ key: null, dir: 'asc' });
  };

  return (
    <div data-testid="page-Sales">
      <PageHeader title="Satislar">
        <Button onClick={() => setFormOpen(true)} data-testid="new-sale">
          + Yeni Satis
        </Button>
      </PageHeader>

      <ErrorMessage message={error} onRetry={load} />

      {formOpen && (
        <SalesForm
          onCreated={(sale) => {
            setFormOpen(false);
            navigate(`/sales/${sale.id}`);
          }}
          onCancel={() => setFormOpen(false)}
        />
      )}

      {!loading && (
        <FilterBar
          resultCount={visible.length}
          totalCount={sales.length}
          hasFilters={hasFilters}
          onClear={clearFilters}
        >
          <FilterField label="Musteri ara">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Musteri adi"
              testid="sale-search"
            />
          </FilterField>
          <FilterField label="Baslangic tarihi">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              data-testid="start-date"
              className={inputClass}
            />
          </FilterField>
          <FilterField label="Bitis tarihi">
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              data-testid="end-date"
              className={inputClass}
            />
          </FilterField>
          <FilterField label="Durum">
            <SelectFilter
              value={status}
              onChange={setStatus}
              options={STATUS_OPTIONS}
              testid="sale-status-filter"
            />
          </FilterField>
        </FilterBar>
      )}

      {loading ? (
        <Loading />
      ) : sales.length === 0 ? (
        <EmptyState message="Henuz satis yok." />
      ) : visible.length === 0 ? (
        <EmptyState message="Arama/filtre kriterlerine uyan satis bulunamadi." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="sales-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th
                  className="text-left px-4 py-2 font-medium cursor-pointer select-none hover:text-indigo-700"
                  onClick={() => setSort(toggleSort(sort, 'id'))}
                  data-testid="sort-id"
                >
                  No
                  <span className="text-indigo-600">
                    {sort.key === 'id' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </span>
                </th>
                <th
                  className="text-left px-4 py-2 font-medium cursor-pointer select-none hover:text-indigo-700"
                  onClick={() => setSort(toggleSort(sort, 'customer_name'))}
                  data-testid="sort-customer"
                >
                  Musteri
                  <span className="text-indigo-600">
                    {sort.key === 'customer_name' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </span>
                </th>
                <th
                  className="text-left px-4 py-2 font-medium cursor-pointer select-none hover:text-indigo-700"
                  onClick={() => setSort(toggleSort(sort, 'sale_date'))}
                  data-testid="sort-date"
                >
                  Tarih
                  <span className="text-indigo-600">
                    {sort.key === 'sale_date' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </span>
                </th>
                <th className="text-right px-4 py-2 font-medium">Urun Sayisi</th>
                <th
                  className="text-right px-4 py-2 font-medium cursor-pointer select-none hover:text-indigo-700"
                  onClick={() => setSort(toggleSort(sort, 'total_amount'))}
                  data-testid="sort-total"
                >
                  Tutar
                  <span className="text-indigo-600">
                    {sort.key === 'total_amount' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </span>
                </th>
                <th className="text-left px-4 py-2 font-medium">Durum</th>
                <th className="text-right px-4 py-2 font-medium">Islem</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <tr key={s.id} data-testid={`sale-row-${s.id}`} className="border-t border-gray-100">
                  <td className="px-4 py-2 text-gray-500">#{s.id}</td>
                  <td className="px-4 py-2 text-gray-800">{s.customer?.name ?? '-'}</td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(s.sale_date)}</td>
                  <td className="px-4 py-2 text-right text-gray-600">{s.items?.length ?? 0}</td>
                  <td className="px-4 py-2 text-right font-medium text-gray-800">
                    {formatMoney(s.total_amount)}
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={statusTone[s.status] ?? 'gray'}>
                      {statusLabel[s.status] ?? s.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      to={`/sales/${s.id}`}
                      data-testid={`detail-${s.id}`}
                      className="text-indigo-600 hover:underline"
                    >
                      Detay
                    </Link>
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
