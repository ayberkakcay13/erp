import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { DocStatusBadge, DocumentActions } from '../components/DocStatus';
import FilterBar, { FilterField, SearchInput, SelectFilter } from '../components/FilterBar';
import PurchaseOrderForm from '../components/PurchaseOrderForm';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  formatMoney,
  formatQty,
} from '../components/ui';
import { purchaseOrderAPI } from '../services/api';
import { matches } from '../utils/filters';

const STATUS_OPTIONS = [
  { value: 'all', label: 'Tum durumlar' },
  { value: 'beklemede', label: 'Beklemede' },
  { value: 'kismi_teslim', label: 'Kismi teslim' },
  { value: 'tamamlandi', label: 'Tamamlandi' },
  { value: 'iptal', label: 'Iptal' },
];

const STATUS_TONE = {
  beklemede: 'yellow',
  kismi_teslim: 'indigo',
  tamamlandi: 'green',
  iptal: 'red',
};

const STATUS_LABEL = {
  beklemede: 'Beklemede',
  kismi_teslim: 'Kismi teslim',
  tamamlandi: 'Tamamlandi',
  iptal: 'Iptal',
};

export default function PurchaseOrders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setOrders(await purchaseOrderAPI.getAll());
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
      orders.filter(
        (o) =>
          matches(o, ['po_number', 'supplier_name', 'note'], search)
          && (statusFilter === 'all' || o.status === statusFilter)
      ),
    [orders, search, statusFilter]
  );

  const act = async (order, action, reason) => {
    setBusyId(order.id);
    setError('');
    try {
      if (action === 'submit') {
        await purchaseOrderAPI.submit(order.id);
        setNotice('Siparis onaylandi.');
      } else {
        await purchaseOrderAPI.cancel(order.id, reason);
        setNotice('Siparis iptal edildi.');
      }
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div data-testid="page-PurchaseOrders">
      <PageHeader title="Satin Alma Siparisleri">
        <Button onClick={() => setFormOpen(true)} data-testid="new-purchase-order">
          + Yeni Siparis
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
        <PurchaseOrderForm
          onCreated={(order) => {
            setFormOpen(false);
            setNotice(`${order.po_number ?? 'Taslak siparis'} kaydedildi.`);
            load();
          }}
          onCancel={() => setFormOpen(false)}
        />
      )}

      {!loading && (
        <FilterBar
          resultCount={visible.length}
          totalCount={orders.length}
          hasFilters={search.trim() !== '' || statusFilter !== 'all'}
          onClear={() => {
            setSearch('');
            setStatusFilter('all');
          }}
        >
          <FilterField label="Ara">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Siparis no veya tedarikci"
              testid="po-search"
            />
          </FilterField>
          <FilterField label="Teslim durumu">
            <SelectFilter
              value={statusFilter}
              onChange={setStatusFilter}
              options={STATUS_OPTIONS}
              testid="po-status-filter"
            />
          </FilterField>
        </FilterBar>
      )}

      {loading ? (
        <Loading />
      ) : orders.length === 0 ? (
        <EmptyState message="Henuz satin alma siparisi yok." />
      ) : visible.length === 0 ? (
        <EmptyState message="Filtreye uyan siparis bulunamadi." />
      ) : (
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="w-full text-sm" data-testid="purchase-orders-table">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Siparis No</th>
                <th className="text-left px-4 py-2 font-medium">Tedarikci</th>
                <th className="text-left px-4 py-2 font-medium">Tarih</th>
                <th className="text-left px-4 py-2 font-medium">Beklenen</th>
                <th className="text-right px-4 py-2 font-medium">Tutar</th>
                <th className="text-left px-4 py-2 font-medium">Teslim</th>
                <th className="text-left px-4 py-2 font-medium">Belge</th>
                <th className="text-right px-4 py-2 font-medium">Islemler</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((o) => (
                <Fragment key={o.id}>
                  <tr
                    data-testid={`po-row-${o.id}`}
                    className="border-t border-gray-100"
                  >
                    <td className="px-4 py-2 font-mono text-xs text-gray-700">
                      <button
                        type="button"
                        onClick={() => setExpanded(expanded === o.id ? null : o.id)}
                        className="text-indigo-700 hover:underline"
                        data-testid={`po-expand-${o.id}`}
                      >
                        {o.po_number ?? `#${o.id} (taslak)`}
                      </button>
                    </td>
                    <td className="px-4 py-2 text-gray-800">{o.supplier_name}</td>
                    <td className="px-4 py-2 text-gray-600">{formatDate(o.order_date)}</td>
                    <td className="px-4 py-2 text-gray-600">
                      {o.expected_date ? formatDate(o.expected_date) : '-'}
                    </td>
                    <td className="px-4 py-2 text-right font-medium">
                      {formatMoney(o.grand_total)}
                    </td>
                    <td className="px-4 py-2">
                      <Badge tone={STATUS_TONE[o.status] ?? 'gray'}>
                        {STATUS_LABEL[o.status] ?? o.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-2">
                      <DocStatusBadge docstatus={o.docstatus} testid={`po-doc-${o.id}`} />
                    </td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">
                      <Link
                        to={`/purchase/match/${o.id}`}
                        className="text-indigo-600 hover:underline text-xs mr-3"
                        data-testid={`po-match-${o.id}`}
                      >
                        Eslestirme
                      </Link>
                      <DocumentActions
                        doc={o}
                        busy={busyId === o.id}
                        onSubmit={() => act(o, 'submit')}
                        onCancel={(reason) => act(o, 'cancel', reason)}
                        testidPrefix={`po-${o.id}`}
                      />
                    </td>
                  </tr>
                  {expanded === o.id && (
                    <tr className="bg-gray-50">
                      <td colSpan={8} className="px-6 py-3">
                        <table className="w-full text-xs">
                          <thead className="text-gray-500">
                            <tr>
                              <th className="text-left py-1">Urun</th>
                              <th className="text-right py-1">Siparis</th>
                              <th className="text-right py-1">Gelen</th>
                              <th className="text-right py-1">Kalan</th>
                              <th className="text-right py-1">Birim Fiyat</th>
                            </tr>
                          </thead>
                          <tbody>
                            {o.items.map((item) => (
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
                                  {formatQty(item.received_quantity)}
                                </td>
                                <td className="py-1 text-right text-amber-700">
                                  {formatQty(item.remaining_quantity)}
                                </td>
                                <td className="py-1 text-right">
                                  {formatMoney(item.unit_price)}
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
