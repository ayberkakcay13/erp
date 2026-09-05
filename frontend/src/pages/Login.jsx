import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button, ErrorMessage, Field, inputClass } from '../components/ui';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Korumali bir sayfadan yonlendirildiyse giristen sonra oraya don
  const from = location.state?.from ?? '/';

  // Sadece admin'in girebildigi sayfalar
  const ADMIN_ONLY = ['/users'];

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const loggedIn = await login(email, password);
      // Giren kullanici oraya giremiyorsa (ornegin cikis yapan admin /users'tayken
      // simdi bir sales giris yaptiysa) Dashboard'a gonder
      const canGoBack = !ADMIN_ONLY.includes(from) || loggedIn.role === 'admin';
      navigate(canGoBack ? from : '/', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="page-Login"
      className="min-h-screen bg-gray-50 flex items-center justify-center p-4"
    >
      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-semibold text-indigo-900">ERP System</h1>
          <p className="text-sm text-gray-500 mt-1">Devam etmek icin giris yap</p>
        </div>

        <form
          onSubmit={submit}
          className="bg-white border border-gray-200 rounded p-5 shadow-sm"
        >
          <ErrorMessage message={error} />
          <Field label="E-posta">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              data-testid="login-email"
              className={inputClass}
            />
          </Field>
          <Field label="Sifre">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              data-testid="login-password"
              className={inputClass}
            />
          </Field>
          <Button
            type="submit"
            disabled={busy}
            data-testid="login-submit"
            className="w-full mt-2 py-2"
          >
            {busy ? 'Giris yapiliyor...' : 'Giris Yap'}
          </Button>
        </form>
      </div>
    </div>
  );
}
