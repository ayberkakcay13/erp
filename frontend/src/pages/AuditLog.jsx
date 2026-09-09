import { useCallback, useEffect, useState } from 'react';
import { actionLabel } from '../components/ChangeHistory';
import FilterBar, { FilterField, SelectFilter } from '../components/FilterBar';
import {
  Badge,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  inputClass,
} from '../components/ui';
import { auditAPI } from '../services/api';

const ACTIONS = [
  { value: '', label: 'Tum islemler' },
  { value: 'create', label: 'Olusturuldu' },
  { value: 'update', label: 'Degistirildi' },
  { value: 'delete', label: 'Silindi' },
  { value: 'submit', label: 'Onaylandi' },
  { value: 'cancel', label: 'Iptal edildi' },
];

const actionTone = {
  create: 'green',
  update: 'yellow',
  delete: 'red',
  submit: 'green',
  cancel: 'red',
};

/** Denetim izi (Phase 11). Sadece admin menusunde gorunur. */
export default function AuditLog() {
  const [rows, setRows] = useState([]);
  const [tables, setTables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [table, setTable] = useState('');
  const [action, setAction] = useState('');
  const [recordId, setRecordId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    auditAPI
      .tables()
      .then(setTables)
      .catch((err) => setError(err.message));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = {};
      if (table) params.table = table;
      if (action) params.action = action;
      if (recordId) params.record_id = recordId;
      if (dateFrom) params.from = dateFrom;
      if (dateTo) params.to = dateTo;
      setRows(await auditAPI.list(params));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [table, action, recordId, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  const hasFilters = Boolean(table || action || recordId || dateFrom || dateTo);

  return (
    <div data-testid="page-AuditLog">
      <PageHeader title="Denetim Izi" />
      <ErrorMessage message={error} onRetry={load} />

      <FilterBar
        resultCount={rows.length}
        totalCount={rows.length}
        hasFilters={hasFilters}
        onClear={() => {
          setTable('');
          setAction('');
          setRecordId('');
          setDateFrom('');
          setDateTo('');
        }}
      >
        <FilterField label="Tablo">
          <SelectFilter
            value={table}
            onChange={setTable}
            options={[
              { value: '', label: 'Tum tablolar' },
              ...tables.map((t) => ({ value: t, label: t })),
            ]}
            testid="audit-table"
          />
        </FilterField>
        <FilterField label="Islem">
          <SelectFilter
            value={action}
            onChange={setAction}
            options={ACTIONS}
            testid="audit-action"
          />
        </FilterField>
        <FilterField label="Kayit no">
          <input
            type="number"
            className={`${inputClass} w-28`}
            value={recordId}
            onChange={(e) => setRecordId(e.target.value)}
            data-testid="audit-record"
          />
        </FilterField>
        <FilterField label="Baslangic">
          <input
            type="date"
            className={inputClass}
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            data-testid="audit-from"
          />
        </FilterField>
        <FilterField label="Bitis">
          <input
            type="date"
            className={inputClass}
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            data-testid="audit-to"
          />
        </FilterField>
      </FilterBar>

      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState message="Bu kriterlere uyan kayit yok." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="audit-table-rows">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-left px-4 py-2 font-medium">Tablo</th>
                <th className="text-left px-4 py-2 font-medium">Kayit</th>
                <th className="text-left px-4 py-2 font-medium">Islem</th>
                <th className="text-left px-4 py-2 font-medium">Alan</th>
                <th className="text-left px-4 py-2 font-medium">Eski</th>
                <th className="text-left px-4 py-2 font-medium">Yeni</th>
                <th className="text-left px-4 py-2 font-medium">Kullanici</th>
                <th className="text-left px-4 py-2 font-medium">IP</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-t border-gray-100"
                  data-testid={`audit-row-${row.id}`}
                >
                  <td className="px-4 py-2 text-gray-600 whitespace-nowrap">
                    {formatDate(row.created_at)}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-gray-700">
                    {row.table_name}
                  </td>
                  <td className="px-4 py-2 text-gray-600">#{row.record_id ?? '-'}</td>
                  <td className="px-4 py-2">
                    <Badge tone={actionTone[row.action] ?? 'gray'}>
                      {actionLabel[row.action] ?? row.action}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-gray-600">
                    {row.field_name ?? '-'}
                  </td>
                  <td className="px-4 py-2 text-gray-500 max-w-[12rem] truncate">
                    {row.old_value ?? '-'}
                  </td>
                  <td className="px-4 py-2 text-gray-800 max-w-[12rem] truncate">
                    {row.new_value ?? '-'}
                  </td>
                  <td className="px-4 py-2 text-gray-600 text-xs">
                    {row.user_email ?? (row.user_id ? `#${row.user_id}` : 'sistem')}
                  </td>
                  <td className="px-4 py-2 text-gray-400 text-xs">
                    {row.ip_address ?? '-'}
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
