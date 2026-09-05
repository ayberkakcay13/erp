import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Badge, Button } from './ui';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center px-3 sm:px-6 shrink-0 gap-3">
      <h1 className="text-lg font-semibold text-gray-800">ERP System</h1>
      <span className="ml-1 text-xs text-gray-400 hidden lg:inline">
        Satis, urun ve fatura yonetimi
      </span>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
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
