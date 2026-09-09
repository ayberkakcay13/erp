import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { DocStatusBadge, DocumentActions } from '../components/DocStatus';
import FilterBar, { FilterField, SearchInput } from '../components/FilterBar';
import PurchaseReceiptForm from '../components/PurchaseReceiptForm';
import {
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  formatQty,
} from '../components/ui';
import { purchaseReceiptAPI } from '../services/api';
import { matches } from '../utils/filters';

export default function PurchaseReceipts() {
  const [receipts, setReceipts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setReceipts(await purchaseReceiptAPI.getAll());
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
      receipts.filter((r) =>
        matches(r, ['receipt_number', 'po_number', 'supplier_name', 'note'], search)
      ),
    [receipts, search]
  );

  const act = async (receipt, action, reason) => {
    setBusyId(receipt.id);
    setError('');
    try {
      if (action === 'submit') {
        await purchaseReceiptAPI.submit(receipt.id);
        setNotice('Mal kabul onaylandi, stok guncellendi.');
      } else {
        await purchaseReceiptAPI.cancel(receipt.id, reason);
        setNotice('Mal kabul iptal edildi, stok geri alindi.');
      }
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div data-testid="page-PurchaseReceipts">
      <PageHeader title="Mal Kabul">
        <Button onClick={() => setFormOpen(true)} data-testid="new-purchase-receipt">
          + Yeni Mal Kabul
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
        <PurchaseReceiptForm
          onCreated={(receipt) => {
            setFormOpen(false);
            setNotice(`${receipt.receipt_number ?? 'Taslak mal kabul'} kaydedildi.`);
            load();
          }}
          onCancel={() => setFormOpen(false)}
        />
      )}

      {!loading && (
        <FilterBar
          resultCount={visible.length}
          totalCount={receipts.length}
          hasFilters={search.trim() !== ''}
          onClear={() => setSearch('')}
        >
          <FilterField label="Ara">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Kabul no, siparis no veya tedarikci"
              testid="receipt-search"
            />
          </FilterField>
        </FilterBar>
      )}

      {loading ? (
        <Loading />
      ) : receipts.length === 0 ? (
        <EmptyState message="Henuz mal kabul kaydi yok." />
      ) : visible.length === 0 ? (
        <EmptyState message="Aramaya uyan mal kabul bulunamadi." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="purchase-receipts-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Kabul No</th>
                <th className="text-left px-4 py-2 font-medium">Siparis</th>
                <th className="text-left px-4 py-2 font-medium">Tedarikci</th>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-right px-4 py-2 font-medium">Kalem</th>
                <th className="text-left px-4 py-2 font-medium">Belge</th>
                <th className="text-right px-4 py-2 font-medium">Islemler</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <Fragment key={r.id}>
                  <tr
                    data-testid={`receipt-row-${r.id}`}
                    className="border-t border-gray-100"
                  >
                    <td className="px-4 py-2 font-mono text-xs">
                      <button
                        type="button"
                        onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                        className="text-indigo-700 hover:underline"
                        data-testid={`receipt-expand-${r.id}`}
                      >
                        {r.receipt_number ?? `#${r.id} (taslak)`}
                      </button>
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-500">
                      {r.po_number ?? '-'}
                    </td>
                    <td className="px-4 py-2 text-gray-800">{r.supplier_name}</td>
                    <td className="px-4 py-2 text-gray-600">{formatDate(r.receipt_date)}</td>
                    <td className="px-4 py-2 text-right text-gray-600">{r.items.length}</td>
                    <td className="px-4 py-2">
                      <DocStatusBadge
                        docstatus={r.docstatus}
                        testid={`receipt-doc-${r.id}`}
                      />
                    </td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">
                      <DocumentActions
                        doc={r}
                        busy={busyId === r.id}
                        onSubmit={() => act(r, 'submit')}
                        onCancel={(reason) => act(r, 'cancel', reason)}
                        testidPrefix={`receipt-${r.id}`}
                      />
                    </td>
                  </tr>
                  {expanded === r.id && (
                    <tr className="bg-gray-50">
                      <td colSpan={7} className="px-6 py-3">
                        <table className="w-full text-xs">
                          <thead className="text-gray-500">
                            <tr>
                              <th className="text-left py-1">Urun</th>
                              <th className="text-right py-1">Gelen</th>
                              <th className="text-right py-1">Kabul</th>
                              <th className="text-right py-1">Red</th>
                              <th className="text-right py-1">Stoga Giren</th>
                              <th className="text-left py-1">Red Sebebi</th>
                            </tr>
                          </thead>
                          <tbody>
                            {r.items.map((item) => (
                              <tr key={item.id} className="border-t border-gray-200">
                                <td className="py-1 text-gray-700">
                                  {item.product_name}
                                  <span className="text-gray-400 ml-2 font-mono">
                                    {item.product_sku}
                                  </span>
                                </td>
                                <td className="py-1 text-right">
                                  {formatQty(item.quantity)} {item.uom_code}
                                </td>
                                <td className="py-1 text-right text-green-700">
                                  {formatQty(item.accepted_quantity)}
                                </td>
                                <td className="py-1 text-right text-red-600">
                                  {formatQty(item.rejected_quantity)}
                                </td>
                                <td className="py-1 text-right font-medium">
                                  {formatQty(item.stock_quantity)}
                                </td>
                                <td className="py-1 text-gray-500">
                                  {item.reject_reason || '-'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
