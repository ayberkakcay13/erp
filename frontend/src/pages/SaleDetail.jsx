import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Badge,
  Button,
  ErrorMessage,
  Loading,
  PageHeader,
  formatDate,
  formatMoney,
  inputClass,
} from '../components/ui';
import { invoiceAPI, salesAPI } from '../services/api';
import { statusLabel, statusTone } from './Sales';

export default function SaleDetail() {
  const { id } = useParams();
  const [sale, setSale] = useState(null);
  const [invoice, setInvoice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await salesAPI.getById(id);
      setSale(data);
      // Bu satisin faturasi var mi? Fatura listesinden sale_id ile bul.
      const invoices = await invoiceAPI.getAll();
      setInvoice(invoices.find((inv) => inv.sale_id === data.id) ?? null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const createInvoice = async () => {
    setBusy(true);
    setError('');
    try {
      const created = await invoiceAPI.create(sale.id, { tax_rate: 0.2 });
      setInvoice(created);
      setNotice(`Fatura olusturuldu: ${created.invoice_number}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const changeStatus = async (status) => {
    setBusy(true);
    setError('');
    const wasCancelled = sale.status === 'cancelled';
    try {
      const updated = await salesAPI.updateStatus(sale.id, status);
      setSale(updated);
      let message = `Satis durumu "${statusLabel[status] ?? status}" olarak guncellendi.`;
      // Stok yalnizca "iptal" sinirini gecerken hareket eder
      if (!wasCancelled && status === 'cancelled') {
        message += ' Bu satistaki urunler stoga geri eklendi.';
      } else if (wasCancelled && status !== 'cancelled') {
        message += ' Bu satistaki urunler stoktan tekrar dusuldu.';
      }
      setNotice(message);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Loading />;
  if (error && !sale) return <ErrorMessage message={error} onRetry={load} />;
  if (!sale) return null;

  return (
    <div data-testid="page-SaleDetail">
      <PageHeader title={`Satis #${sale.id}`}>
        <Link to="/sales">
          <Button variant="secondary">Satislara don</Button>
        </Link>
      </PageHeader>

      <ErrorMessage message={error} />
      {notice && (
        <div data-testid="notice" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-4">
          {notice}
        </div>
      )}

      <div className="grid md:grid-cols-3 gap-4 mb-5">
        <div className="bg-white border border-gray-200 rounded p-4" data-testid="customer-card">
          <div className="text-xs uppercase text-gray-400 mb-1">Musteri</div>
          <div className="font-medium text-gray-800" data-testid="customer-name">
            {sale.customer?.name ?? '-'}
          </div>
          <div className="text-sm text-gray-600">{sale.customer?.email}</div>
          <div className="text-sm text-gray-600">{sale.customer?.phone || '-'}</div>
        </div>

        <div className="bg-white border border-gray-200 rounded p-4">
          <div className="text-xs uppercase text-gray-400 mb-1">Satis Bilgisi</div>
          <div className="text-sm text-gray-700">Tarih: {formatDate(sale.sale_date)}</div>
          <div className="text-sm text-gray-700 flex items-center gap-2 mt-1">
            Durum:
            <Badge tone={statusTone[sale.status] ?? 'gray'}>
              {statusLabel[sale.status] ?? sale.status}
            </Badge>
          </div>
          <select
            value={sale.status}
            disabled={busy}
            onChange={(e) => changeStatus(e.target.value)}
            data-testid="status-select"
            className={`${inputClass} mt-2`}
          >
            <option value="pending">Bekliyor</option>
            <option value="completed">Tamamlandi</option>
            <option value="cancelled">Iptal</option>
          </select>
        </div>

        <div className="bg-white border border-gray-200 rounded p-4">
          <div className="text-xs uppercase text-gray-400 mb-1">Toplam Tutar</div>
          <div className="text-2xl font-semibold text-indigo-700" data-testid="sale-total">
            {formatMoney(sale.total_amount)}
          </div>
          <div className="mt-3">
            {invoice ? (
              <div data-testid="invoice-info" className="text-sm">
                <div className="text-gray-700 font-mono text-xs">{invoice.invoice_number}</div>
                <Link to="/invoices" className="text-indigo-600 hover:underline text-sm">
                  Faturalara git
                </Link>
              </div>
            ) : (
              <Button onClick={createInvoice} disabled={busy} data-testid="create-invoice">
                {busy ? 'Olusturuluyor...' : 'Fatura Olustur (KDV %20)'}
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded overflow-x-auto">
        <table className="w-full text-sm" data-testid="sale-items">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Urun</th>
              <th className="text-left px-4 py-2 font-medium">SKU</th>
              <th className="text-right px-4 py-2 font-medium">Miktar</th>
              <th className="text-right px-4 py-2 font-medium">Birim Fiyat</th>
              <th className="text-right px-4 py-2 font-medium">Satir Toplami</th>
            </tr>
          </thead>
          <tbody>
            {sale.items.map((item) => (
              <tr key={item.id} data-testid={`sale-item-${item.id}`} className="border-t border-gray-100">
                <td className="px-4 py-2 text-gray-800">{item.product_name ?? '-'}</td>
                <td className="px-4 py-2 text-gray-500 font-mono text-xs">{item.product_sku ?? '-'}</td>
                <td className="px-4 py-2 text-right">{item.quantity}</td>
                <td className="px-4 py-2 text-right">{formatMoney(item.unit_price)}</td>
                <td className="px-4 py-2 text-right font-medium">{formatMoney(item.total_price)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-200 bg-gray-50">
              <td colSpan={4} className="px-4 py-2 text-right font-medium text-gray-700">
                Toplam
              </td>
              <td className="px-4 py-2 text-right font-semibold text-indigo-700">
                {formatMoney(sale.total_amount)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
