import { useEffect, useState } from 'react';
import { auditAPI } from '../services/api';
import { Badge, EmptyState, ErrorMessage, Loading, formatDate } from './ui';

export const actionLabel = {
  create: 'Olusturuldu',
  update: 'Degistirildi',
  delete: 'Silindi',
  submit: 'Onaylandi',
  cancel: 'Iptal edildi',
};

const actionTone = {
  create: 'green',
  update: 'yellow',
  delete: 'red',
  submit: 'green',
  cancel: 'red',
};

/**
 * Tek bir kaydin degisiklik gecmisi (Phase 11 denetim izi).
 * Sadece admin okuyabildigi icin yetkisiz kullaniciya bilgi notu gosterilir.
 */
export default function ChangeHistory({ table, recordId }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    auditAPI
      .recordHistory(table, recordId)
      .then((data) => !cancelled && setRows(data))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [table, recordId]);

  if (error) {
    return error.includes('yetki') || error.includes('403') ? (
      <p className="text-sm text-gray-500">
        Degisiklik gecmisini yalnizca yoneticiler gorebilir.
      </p>
    ) : (
      <ErrorMessage message={error} />
    );
  }
  if (!rows) return <Loading />;
  if (rows.length === 0) return <EmptyState message="Bu kayit icin degisiklik yok." />;

  return (
    <div className="overflow-x-auto border border-gray-200 rounded">
      <table className="w-full text-sm" data-testid="change-history">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            <th className="text-left px-3 py-2 font-medium">Tarih</th>
            <th className="text-left px-3 py-2 font-medium">Islem</th>
            <th className="text-left px-3 py-2 font-medium">Alan</th>
            <th className="text-left px-3 py-2 font-medium">Eski</th>
            <th className="text-left px-3 py-2 font-medium">Yeni</th>
            <th className="text-left px-3 py-2 font-medium">Kullanici</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-gray-100">
              <td className="px-3 py-2 text-gray-600 whitespace-nowrap">
                {formatDate(row.created_at)}
              </td>
              <td className="px-3 py-2">
                <Badge tone={actionTone[row.action] ?? 'gray'}>
                  {actionLabel[row.action] ?? row.action}
                </Badge>
              </td>
              <td className="px-3 py-2 font-mono text-xs text-gray-600">
                {row.field_name ?? '-'}
              </td>
              <td className="px-3 py-2 text-gray-500">{row.old_value ?? '-'}</td>
              <td className="px-3 py-2 text-gray-800">{row.new_value ?? '-'}</td>
              <td className="px-3 py-2 text-gray-600 text-xs">
                {row.user_email ?? (row.user_id ? `#${row.user_id}` : 'sistem')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
