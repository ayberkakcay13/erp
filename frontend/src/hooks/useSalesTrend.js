import { useCallback, useEffect, useState } from 'react';
import { addMonths, addYears } from '../components/Dashboard/utils/dateUtils';

/**
 * Phase 19: zaman araligi (Gunluk/Haftalik/Aylik/Yillik) + tarih navigasyonu
 * state'ini ve veri yuklemesini yonetir. `fetchData(timeRange, date)` cagirana
 * ozgudur - Dashboard, musteri bazli ve urun bazli grafikler SalesChartWidget'i
 * ayni hook ile ama farkli fetchData fonksiyonlariyla kullanir.
 */
export function useSalesTrend(fetchData) {
  const [timeRange, setTimeRange] = useState('monthly');
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await fetchData(timeRange, selectedDate));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [fetchData, timeRange, selectedDate]);

  useEffect(() => {
    load();
  }, [load]);

  const step = (n) => {
    setSelectedDate((d) => (timeRange === 'yearly' ? addYears(d, n) : addMonths(d, n)));
  };

  return { timeRange, setTimeRange, selectedDate, step, data, loading, error, reload: load };
}
