import { useCallback, useEffect, useState } from 'react';
import { productAPI } from '../services/api';

/**
 * Phase 19: urune ait siparisleri yukler (ProductDetailModal - Devam Eden/Son
 * Siparisler sekmeleri). useCustomerOrders ile ayni desen - productAPI
 * (services/api.js, axios) uzerinden gecer.
 */
export function useProductOrders(productId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await productAPI.orders(productId));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, loading, error, reload };
}
