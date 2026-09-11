import { useCallback, useState } from 'react';
import { productAPI } from '../../services/api';
import { formatDate } from '../Dashboard/utils/dateUtils';
import { useProductOrders } from '../../hooks/useProductOrders';
import DetailModal from '../Shared/DetailModal';
import TabView from '../Shared/TabView';
import OrdersTable from '../Shared/OrdersTable';
import SalesChartWidget from '../Shared/SalesChartWidget';
import { ErrorMessage, Loading } from '../ui';

/** Date -> "yyyy-MM-dd", backend'e query param olarak gonderilir */
const isoDate = (date) => formatDate(date, 'yyyy-MM-dd');

const TABS = [
  { key: 'ongoing', label: 'Devam Eden Siparisler' },
  { key: 'recent', label: 'Son Siparisler' },
  { key: 'trend', label: 'Satis Trendi' },
];

/** Phase 17-19: Urun satirina tiklaninca acilan detay penceresi (backend'den yuklenir) */
export default function ProductDetailModal({ product, onClose }) {
  const [tab, setTab] = useState('ongoing');
  const { data: orders, loading, error, reload } = useProductOrders(product.id);

  const fetchTrend = useCallback(
    (range, date) => productAPI.salesTrend(product.id, range, isoDate(date)),
    [product.id]
  );

  const ongoing = orders?.filter((o) => o.status === 'pending' || o.status === 'processing') ?? [];
  const recent = orders
    ? [...orders].sort((a, b) => (a.order_date < b.order_date ? 1 : -1)).slice(0, 5)
    : [];

  return (
    <DetailModal
      title={product.name}
      subtitle={product.sku}
      onClose={onClose}
      testid="product-detail-modal"
    >
      <TabView tabs={TABS} active={tab} onChange={setTab}>
        {tab !== 'trend' && loading && <Loading label="Siparisler yukleniyor..." />}
        {tab !== 'trend' && !loading && error && <ErrorMessage message={error} onRetry={reload} />}
        {tab === 'ongoing' && !loading && !error && (
          <OrdersTable
            orders={ongoing}
            secondColumn={{ label: 'Musteri', field: 'customer' }}
            emptyMessage="Devam eden siparis yok."
          />
        )}
        {tab === 'recent' && !loading && !error && (
          <OrdersTable
            orders={recent}
            secondColumn={{ label: 'Musteri', field: 'customer' }}
            emptyMessage="Henuz siparis yok."
          />
        )}
        {tab === 'trend' && <SalesChartWidget fetchData={fetchTrend} />}
      </TabView>
    </DetailModal>
  );
}
