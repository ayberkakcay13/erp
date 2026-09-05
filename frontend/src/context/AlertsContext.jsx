import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { alertAPI } from '../services/api';
import { useAuth } from './AuthContext';

/**
 * Uyari ozeti tek yerden yonetiliyor: hem Dashboard'daki panel hem navbar
 * rozeti ayni veriyi kullansin, iki ayri istek atilmasin.
 */
const AlertsContext = createContext(null);

export function AlertsProvider({ children }) {
  const { token } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    if (!token) {
      setSummary(null);
      return;
    }
    setLoading(true);
    setError('');
    try {
      setSummary(await alertAPI.summary());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ summary, loading, error, refresh }),
    [summary, loading, error, refresh]
  );
  return <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>;
}

export function useAlerts() {
  const ctx = useContext(AlertsContext);
  if (!ctx) throw new Error('useAlerts, AlertsProvider icinde kullanilmali');
  return ctx;
}
