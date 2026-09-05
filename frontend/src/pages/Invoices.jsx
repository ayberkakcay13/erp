import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
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
import { customerAPI, invoiceAPI } from '../services/api';

const tone = { draft: 'gray', issued: 'blue', paid: 'green' };
const label = { draft: 'Taslak', issued: 'Kesildi', paid: 'Odendi' };

function InvoiceModal({ invoice, customerName, onClose, onStatusChange, busy }) {
  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-10"
      onClick={onClose}
      data-testid="invoice-modal"
    >
      <div
        className="bg-white rounded shadow-lg max-w-md w-full p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-gray-800 mb-1">Fatura Detayi</h3>
        <p className="font-mono text-xs text-gray-500 mb-4" data-testid="modal-number">
          {invoice.invoice_number}
        </p>

        <dl className="text-sm space-y-2 mb-4">
          <div className="flex justify-between">
            <dt className="text-gray-500">Musteri</dt>
            <dd className="text-gray-800">{customerName}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-gray-500">Satis</dt>
            <dd>
              <Link to={`/sales/${invoice.sale_id}`} className="text-indigo-600 hover:underline">
                #{invoice.sale_id}
              </Link>
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-gray-500">Kesim Tarihi</dt>
            <dd className="text-gray-800">{formatDate(invoice.issued_date)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-gray-500">Tutar (KDV dahil)</dt>
            <dd className="font-semibold text-indigo-700" data-testid="modal-total">
              {formatMoney(invoice.total_amount)}
            </dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-gray-500">Durum</dt>
            <dd>
              <Badge tone={tone[invoice.status] ?? 'gray'}>
                {label[invoice.status] ?? invoice.status}
              </Badge>
            </dd>
          </div>
        </dl>

        <select
          value={invoice.status}
          disabled={busy}
          onChange={(e) => onStatusChange(invoice, e.target.value)}
          data-testid="modal-status"
          className={inputClass}
        >
          <option value="draft">Taslak</option>
          <option value="issued">Kesildi</option>
          <option value="paid">Odendi</option>
        </select>

        <div className="mt-4 text-right">
          <Button variant="secondary" onClick={onClose} data-testid="modal-close">
            Kapat
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function Invoices() {
  const [invoices, setInvoices] = useState([]);
  const [customers, setCustomers] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [inv, cust] = await Promise.all([invoiceAPI.getAll(), customerAPI.getAll()]);
      setInvoices(inv);
      setCustomers(Object.fromEntries(cust.map((c) => [c.id, c.name])));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const changeStatus = async (invoice, status) => {
    setBusy(true);
    setError('');
    try {
      const updated = await invoiceAPI.updateStatus(invoice.id, status);
      setInvoices((list) => list.map((i) => (i.id === updated.id ? updated : i)));
      setSelected((cur) => (cur && cur.id === updated.id ? updated : cur));
      setNotice(`${updated.invoice_number} -> ${label[status] ?? status}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="page-Invoices">
      <PageHeader title="Faturalar" />

      <ErrorMessage message={error} onRetry={load} />
      {notice && (
        <div data-testid="notice" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-4">
          {notice}
        </div>
      )}

      {loading ? (
        <Loading />
      ) : invoices.length === 0 ? (
        <EmptyState message="Henuz fatura yok. Bir satis detayindan fatura olusturabilirsin." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="invoices-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Fatura No</th>
                <th className="text-left px-4 py-2 font-medium">Musteri</th>
                <th className="text-left px-4 py-2 font-medium">Satis</th>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-right px-4 py-2 font-medium">Tutar</th>
                <th className="text-left px-4 py-2 font-medium">Durum</th>
                <th className="text-right px-4 py-2 font-medium">Islem</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id} data-testid={`invoice-row-${inv.id}`} className="border-t border-gray-100">
                  <td className="px-4 py-2 font-mono text-xs text-gray-700">{inv.invoice_number}</td>
                  <td className="px-4 py-2 text-gray-800">{customers[inv.customer_id] ?? '-'}</td>
                  <td className="px-4 py-2">
                    <Link to={`/sales/${inv.sale_id}`} className="text-indigo-600 hover:underline">
                      #{inv.sale_id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(inv.issued_date)}</td>
                  <td className="px-4 py-2 text-right font-medium text-gray-800">
                    {formatMoney(inv.total_amount)}
                  </td>
                  <td className="px-4 py-2" data-testid={`invoice-status-${inv.id}`}>
                    <Badge tone={tone[inv.status] ?? 'gray'}>
                      {label[inv.status] ?? inv.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Button
                      variant="secondary"
                      onClick={() => setSelected(inv)}
                      data-testid={`open-${inv.id}`}
                    >
                      Detay
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <InvoiceModal
          invoice={selected}
          customerName={customers[selected.customer_id] ?? '-'}
          busy={busy}
          onStatusChange={changeStatus}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
