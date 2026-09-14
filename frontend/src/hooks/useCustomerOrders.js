import { useCallback, useEffect, useState } from 'react';
import { customerAPI } from '../services/api';

/**
 * Phase 19: musteriye ait siparisleri yukler (CustomerDetailModal - Devam
 * Eden/Son Siparisler sekmeleri). Auth/base URL/hata normalizasyonu
 * customerAPI (services/api.js, axios) uzerinden gelir - ciplak fetch()
 * kullanilmaz, yoksa Authorization header'i gitmez ve istek 401 doner.
 */
export function useCustomerOrders(customerId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await customerAPI.orders(customerId));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, loading, error, reload };
}
