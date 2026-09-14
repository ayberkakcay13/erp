import { useCallback, useState } from 'react';
import { customerAPI } from '../../services/api';
import { formatDate } from '../Dashboard/utils/dateUtils';
import { useCustomerOrders } from '../../hooks/useCustomerOrders';
import DetailModal from '../Shared/DetailModal';
import TabView from '../Shared/TabView';
import OrdersTable from '../Shared/OrdersTable';
import SalesChartWidget from '../Shared/SalesChartWidget';
import { ErrorMessage, Loading } from '../ui';

const TABS = [
  { key: 'ongoing', label: 'Devam Eden Siparisler' },
  { key: 'recent', label: 'Son Siparisler' },
  { key: 'trend', label: 'Satis Trendi' },
];

/** Date -> "yyyy-MM-dd", backend'e query param olarak gonderilir */
const isoDate = (date) => formatDate(date, 'yyyy-MM-dd');

/** Phase 17-19: Musteri satirina tiklaninca acilan detay penceresi (backend'den yuklenir) */
export default function CustomerDetailModal({ customer, onClose }) {
  const [tab, setTab] = useState('ongoing');
  const { data: orders, loading, error, reload } = useCustomerOrders(customer.id);

  const fetchTrend = useCallback(
    (range, date) => customerAPI.salesTrend(customer.id, range, isoDate(date)),
    [customer.id]
  );

  const ongoing = orders?.filter((o) => o.status === 'pending' || o.status === 'processing') ?? [];
  const recent = orders
    ? [...orders].sort((a, b) => (a.order_date < b.order_date ? 1 : -1)).slice(0, 5)
    : [];

  return (
    <DetailModal
      title={customer.name}
      subtitle={customer.email}
      onClose={onClose}
      testid="customer-detail-modal"
    >
      <TabView tabs={TABS} active={tab} onChange={setTab}>
        {tab !== 'trend' && loading && <Loading label="Siparisler yukleniyor..." />}
        {tab !== 'trend' && !loading && error && <ErrorMessage message={error} onRetry={reload} />}
        {tab === 'ongoing' && !loading && !error && (
          <OrdersTable
            orders={ongoing}
            secondColumn={{ label: 'Urun', field: 'product' }}
            emptyMessage="Devam eden siparis yok."
          />
        )}
        {tab === 'recent' && !loading && !error && (
          <OrdersTable
            orders={recent}
            secondColumn={{ label: 'Urun', field: 'product' }}
            emptyMessage="Henuz siparis yok."
          />
        )}
        {tab === 'trend' && <SalesChartWidget fetchData={fetchTrend} />}
      </TabView>
    </DetailModal>
  );
}
