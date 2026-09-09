import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { authAPI, setAuthToken, setUnauthorizedHandler, tenantAPI } from '../services/api';

const AuthContext = createContext(null);

const TOKEN_KEY = 'erp_token';
const USER_KEY = 'erp_user';

function readStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(readStoredUser);
  const [loading, setLoading] = useState(Boolean(localStorage.getItem(TOKEN_KEY)));
  // Phase 12: bu firmada acik olan moduller. Menu ve sayfalar buna gore kurulur.
  const [modules, setModules] = useState([]);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setAuthToken(null);
    setToken(null);
    setUser(null);
    setModules([]);
    setLoading(false);
  }, []);

  // Token'i axios'a bagla; 401 gelirse oturumu kapat
  useEffect(() => {
    setAuthToken(token);
    setUnauthorizedHandler(logout);
  }, [token, logout]);

  // Sayfa yenilendiginde saklanan token hala gecerli mi diye backend'e sor
  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setAuthToken(token);
    authAPI
      .me()
      .then((fresh) => {
        if (cancelled) return;
        setUser(fresh);
        localStorage.setItem(USER_KEY, JSON.stringify(fresh));
        // Modul listesi oturumla birlikte tazelenir; kapali modul menude cikmaz
        return tenantAPI.myModules().then((data) => {
          if (!cancelled) setModules(data.enabled ?? []);
        });
      })
      .catch(() => {
        if (!cancelled) logout();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Sadece ilk yuklemede ve token degistiginde calissin
  }, [token, logout]);

  const login = useCallback(async (email, password) => {
    const data = await authAPI.login(email, password);
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    setAuthToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    try {
      const info = await tenantAPI.myModules();
      setModules(info.enabled ?? []);
    } catch {
      setModules([]); // modul bilgisi alinamazsa menu en dar haliyle acilir
    }
    return data.user;
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      login,
      logout,
      isAdmin: user?.role === 'admin',
      isSuperadmin: Boolean(user?.is_superadmin),
      modules,
      hasModule: (code) => modules.length === 0 || modules.includes(code),
    }),
    [user, token, loading, login, logout, modules]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth, AuthProvider icinde kullanilmali');
  return ctx;
}
