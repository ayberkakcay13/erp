import { useNavigate } from 'react-router-dom';
import { useAlerts } from '../context/AlertsContext';
import { useAuth } from '../context/AuthContext';
import { Badge, Button } from './ui';

export default function Navbar() {
  const { user, logout } = useAuth();
  const { summary } = useAlerts();
  const navigate = useNavigate();
  const alertCount = summary?.total ?? 0;

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  // Zile tiklayinca Dashboard'daki uyari paneline git
  const goToAlerts = () => {
    navigate('/');
    setTimeout(() => {
      document.getElementById('alerts-panel')?.scrollIntoView({ behavior: 'smooth' });
    }, 300);
  };

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center px-3 sm:px-6 shrink-0 gap-3">
      <h1 className="text-lg font-semibold text-gray-800">ERP System</h1>
      <span className="ml-1 text-xs text-gray-400 hidden lg:inline">
        Satis, urun ve fatura yonetimi
      </span>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        {user && (
          <button
            type="button"
            onClick={goToAlerts}
            data-testid="alert-bell"
            title={alertCount > 0 ? `${alertCount} uyari var` : 'Uyari yok'}
            className="relative p-1.5 rounded hover:bg-gray-100 transition-colors text-lg leading-none"
          >
            <span aria-hidden>🔔</span>
            {alertCount > 0 && (
              <span
                data-testid="alert-bell-count"
                className="absolute -top-0.5 -right-0.5 bg-red-600 text-white text-[10px] font-bold rounded-full min-w-[16px] h-4 px-1 flex items-center justify-center"
              >
                {alertCount > 99 ? '99+' : alertCount}
              </span>
            )}
          </button>
        )}
        {user && (
          <span className="text-sm text-gray-600 flex items-center gap-2" data-testid="current-user">
            <span className="hidden sm:inline">{user.full_name || user.email}</span>
            <Badge tone={user.role === 'admin' ? 'blue' : 'gray'}>{user.role}</Badge>
          </span>
        )}
        <Button variant="secondary" onClick={handleLogout} data-testid="logout">
          Cikis Yap
        </Button>
      </div>
    </header>
  );
}
