import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAlerts } from '../context/AlertsContext';
import { Badge, ErrorMessage, Loading, formatMoney } from './ui';

function AlertRow({ children, onClick, testid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors flex items-center gap-3"
    >
      {children}
    </button>
  );
}

export default function AlertsPanel() {
  const { summary, loading, error, refresh } = useAlerts();
  const [expanded, setExpanded] = useState(null);
  const navigate = useNavigate();

  if (loading && !summary) return <Loading label="Uyarilar kontrol ediliyor..." />;
  if (error) return <ErrorMessage message={error} onRetry={refresh} />;
  if (!summary) return null;

  const low = summary.low_stock;
  const overdue = summary.overdue_invoices;
  const hasAlerts = summary.total > 0;

  if (!hasAlerts) {
    return (
      <div
        data-testid="alerts-panel"
        className="bg-green-50 border border-green-200 rounded p-4 mb-6 flex items-center gap-3"
      >
        <span className="text-xl">✅</span>
        <div>
          <div className="text-sm font-medium text-green-800" data-testid="alerts-ok">
            Her sey yolunda
          </div>
          <div className="text-xs text-green-700">
            Stoklar yeterli, vadesi gecmis fatura yok.
          </div>
        </div>
      </div>
    );
  }

  const toggle = (key) => setExpanded(expanded === key ? null : key);

  return (
    <div
      id="alerts-panel"
      data-testid="alerts-panel"
      className="bg-white border border-amber-300 rounded mb-6 overflow-hidden"
    >
      <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center gap-2">
        <span>🔔</span>
        <span className="text-sm font-medium text-amber-900">
          Dikkat gerektiren {summary.total} konu var
        </span>
      </div>

      <div className="divide-y divide-gray-100">
        {low.count > 0 && (
          <div>
            <AlertRow onClick={() => toggle('low')} testid="alert-low-stock">
              <Badge tone={low.out_of_stock > 0 ? 'red' : 'yellow'}>{low.count}</Badge>
              <span className="text-sm text-gray-800 flex-1">
                <span data-testid="alert-low-stock-text">
                  {low.count} urunde stok azaldi
                </span>
                {low.out_of_stock > 0 && (
                  <span className="text-red-600 text-xs ml-2">
                    ({low.out_of_stock} tanesi tukendi)
                  </span>
                )}
              </span>
              <span className="text-xs text-gray-400">{expanded === 'low' ? 'gizle' : 'detay'}</span>
            </AlertRow>
            {expanded === 'low' && (
              <div className="px-4 pb-3" data-testid="alert-low-stock-detail">
                <ul className="text-sm divide-y divide-gray-100 border border-gray-100 rounded">
                  {low.items.slice(0, 8).map((p) => (
                    <li key={p.id} className="flex items-center gap-3 px-3 py-1.5">
                      <span className="flex-1 text-gray-700">{p.name}</span>
                      <span className="font-mono text-xs text-gray-400">{p.sku}</span>
                      <Badge tone={p.stock === 0 ? 'red' : 'yellow'}>{p.stock} adet</Badge>
                    </li>
                  ))}
                </ul>
                {low.items.length > 8 && (
                  <p className="text-xs text-gray-400 mt-1">
                    ve {low.items.length - 8} urun daha...
                  </p>
                )}
                {/* Phase 8 ile birlikte: Urunler sayfasini "az stok" filtresiyle ac */}
                <button
                  type="button"
                  onClick={() => navigate('/products?stock=low')}
                  data-testid="alert-goto-products"
                  className="text-indigo-600 hover:underline text-sm mt-2"
                >
                  Urunler sayfasinda goster →
                </button>
              </div>
            )}
          </div>
        )}

        {overdue.count > 0 && (
          <div>
            <AlertRow onClick={() => toggle('overdue')} testid="alert-overdue">
              <Badge tone="red">{overdue.count}</Badge>
              <span className="text-sm text-gray-800 flex-1">
                <span data-testid="alert-overdue-text">
                  {overdue.count} fatura {overdue.days}+ gundur odenmedi
                </span>
                <span className="text-xs text-gray-500 ml-2">
                  (toplam {formatMoney(overdue.total_amount)})
                </span>
              </span>
              <span className="text-xs text-gray-400">
                {expanded === 'overdue' ? 'gizle' : 'detay'}
              </span>
            </AlertRow>
            {expanded === 'overdue' && (
              <div className="px-4 pb-3" data-testid="alert-overdue-detail">
                <ul className="text-sm divide-y divide-gray-100 border border-gray-100 rounded">
                  {overdue.items.slice(0, 8).map((inv) => (
                    <li key={inv.id} className="flex items-center gap-3 px-3 py-1.5">
                      <span className="font-mono text-xs text-gray-500">
                        {inv.invoice_number}
                      </span>
                      <span className="flex-1 text-gray-700">{inv.customer_name ?? '-'}</span>
                      <span className="text-gray-600">{formatMoney(inv.total_amount)}</span>
                      <Badge tone="red">{inv.days_overdue} gun</Badge>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => navigate('/invoices?status=issued')}
                  data-testid="alert-goto-invoices"
                  className="text-indigo-600 hover:underline text-sm mt-2"
                >
                  Faturalar sayfasinda goster →
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
