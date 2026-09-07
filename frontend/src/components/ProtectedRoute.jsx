import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loading } from './ui';

/**
 * Giris yapmamis kullaniciyi /login'e yollar.
 * adminOnly verilirse sales rolundeki kullanici da giremez.
 * superadminOnly (Phase 12) platform sahibine ozel sayfalar icindir -
 * firma yoneticisi bunlara erisemez.
 */
export default function ProtectedRoute({
  children,
  adminOnly = false,
  superadminOnly = false,
}) {
  const { token, user, loading, isAdmin, isSuperadmin } = useAuth();
  const location = useLocation();

  // Saklanan token dogrulanana kadar bekle, yoksa bir an login ekrani gorunur
  if (loading) return <Loading label="Oturum kontrol ediliyor..." />;

  if (!token || !user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (superadminOnly && !isSuperadmin) {
    return (
      <div data-testid="forbidden" className="bg-white border border-gray-200 rounded p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-1">Bu sayfaya erisemezsin</h2>
        <p className="text-sm text-gray-600">
          Bu bolum platform yoneticisine ozeldir.
        </p>
      </div>
    );
  }

  if (adminOnly && !isAdmin) {
    return (
      <div data-testid="forbidden" className="bg-white border border-gray-200 rounded p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-1">Bu sayfaya erisemezsin</h2>
        <p className="text-sm text-gray-600">
          Bu bolum sadece admin kullanicilar icindir. Rolun: {user.role}
        </p>
      </div>
    );
  }

  return children;
}
