import { useCallback, useEffect, useMemo, useState } from 'react';
import { DocStatusBadge, DocumentActions } from '../components/DocStatus';
import FilterBar, { FilterField, SearchInput, SelectFilter } from '../components/FilterBar';
import PurchaseInvoiceForm from '../components/PurchaseInvoiceForm';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  formatMoney,
} from '../components/ui';
import { purchaseInvoiceAPI } from '../services/api';
import { matches } from '../utils/filters';

const PAYMENT_OPTIONS = [
  { value: 'all', label: 'Tum odeme durumlari' },
  { value: 'odenmedi', label: 'Odenmedi' },
  { value: 'kismi', label: 'Kismi odendi' },
  { value: 'odendi', label: 'Odendi' },
];

const PAYMENT_TONE = { odenmedi: 'red', kismi: 'yellow', odendi: 'green' };
const PAYMENT_LABEL = {
  odenmedi: 'Odenmedi',
  kismi: 'Kismi',
  odendi: 'Odendi',
};

export default function PurchaseInvoices() {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [search, setSearch] = useState('');
  const [paymentFilter, setPaymentFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setInvoices(await purchaseInvoiceAPI.getAll());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(
    () =>
      invoices.filter(
        (i) =>
          matches(i, ['invoice_number', 'internal_number', 'supplier_name'], search)
          && (paymentFilter === 'all' || i.payment_status === paymentFilter)
      ),
    [invoices, search, paymentFilter]
  );

  const act = async (invoice, action, reason) => {
    setBusyId(invoice.id);
    setError('');
    try {
      if (action === 'submit') {
        await purchaseInvoiceAPI.submit(invoice.id);
        setNotice('Fatura onaylandi.');
      } else {
        await purchaseInvoiceAPI.cancel(invoice.id, reason);
        setNotice('Fatura iptal edildi.');
      }
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const setPaymentStatus = async (invoice, value) => {
    setBusyId(invoice.id);
    setError('');
    try {
      await purchaseInvoiceAPI.update(invoice.id, { payment_status: value });
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div data-testid="page-PurchaseInvoices">
      <PageHeader title="Alis Faturalari">
        <Button onClick={() => setFormOpen(true)} data-testid="new-purchase-invoice">
          + Yeni Alis Faturasi
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
        <PurchaseInvoiceForm
          onCreated={(invoice) => {
            setFormOpen(false);
            setNotice(`${invoice.internal_number ?? 'Taslak fatura'} kaydedildi.`);
            load();
          }}
          onCancel={() => setFormOpen(false)}
        />
      )}

      {!loading && (
        <FilterBar
          resultCount={visible.length}
          totalCount={invoices.length}
          hasFilters={search.trim() !== '' || paymentFilter !== 'all'}
          onClear={() => {
            setSearch('');
            setPaymentFilter('all');
          }}
        >
          <FilterField label="Ara">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Fatura no veya tedarikci"
              testid="invoice-search"
            />
          </FilterField>
          <FilterField label="Odeme durumu">
            <SelectFilter
              value={paymentFilter}
              onChange={setPaymentFilter}
              options={PAYMENT_OPTIONS}
              testid="invoice-payment-filter"
            />
          </FilterField>
        </FilterBar>
      )}

      {loading ? (
        <Loading />
      ) : invoices.length === 0 ? (
        <EmptyState message="Henuz alis faturasi yok." />
      ) : visible.length === 0 ? (
        <EmptyState message="Filtreye uyan fatura bulunamadi." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="purchase-invoices-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Ic No</th>
                <th className="text-left px-4 py-2 font-medium">Tedarikci Fatura No</th>
                <th className="text-left px-4 py-2 font-medium">Tedarikci</th>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-left px-4 py-2 font-medium">Vade</th>
                <th className="text-right px-4 py-2 font-medium">Tutar</th>
                <th className="text-left px-4 py-2 font-medium">Odeme</th>
                <th className="text-left px-4 py-2 font-medium">Belge</th>
                <th className="text-right px-4 py-2 font-medium">Islemler</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((i) => (
                <tr
                  key={i.id}
                  data-testid={`invoice-row-${i.id}`}
                  className="border-t border-gray-100"
                >
                  <td className="px-4 py-2 font-mono text-xs text-gray-700">
                    {i.internal_number ?? `#${i.id}`}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-gray-500">
                    {i.invoice_number}
                  </td>
                  <td className="px-4 py-2 text-gray-800">{i.supplier_name}</td>
                  <td className="px-4 py-2 text-gray-600">{formatDate(i.invoice_date)}</td>
                  <td className="px-4 py-2 text-gray-600">
                    {i.due_date ? formatDate(i.due_date) : '-'}
                  </td>
                  <td className="px-4 py-2 text-right font-medium">
                    {formatMoney(i.grand_total)}
                  </td>
                  <td className="px-4 py-2">
                    <select
                      value={i.payment_status}
                      disabled={busyId === i.id}
                      onChange={(e) => setPaymentStatus(i, e.target.value)}
                      data-testid={`invoice-payment-${i.id}`}
                      className="text-xs border border-gray-200 rounded px-1 py-0.5"
                    >
                      {PAYMENT_OPTIONS.filter((o) => o.value !== 'all').map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                    <div className="mt-1">
                      <Badge tone={PAYMENT_TONE[i.payment_status] ?? 'gray'}>
                        {PAYMENT_LABEL[i.payment_status] ?? i.payment_status}
                      </Badge>
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <DocStatusBadge docstatus={i.docstatus} testid={`invoice-doc-${i.id}`} />
                  </td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <DocumentActions
                      doc={i}
                      busy={busyId === i.id}
                      onSubmit={() => act(i, 'submit')}
                      onCancel={(reason) => act(i, 'cancel', reason)}
                      testidPrefix={`invoice-${i.id}`}
                    />
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
