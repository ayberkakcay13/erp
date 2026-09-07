import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const links = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/customers', label: 'Musteriler' },
  { to: '/products', label: 'Urunler' },
  { to: '/sales', label: 'Satislar' },
  { to: '/invoices', label: 'Faturalar' },
  { to: '/stock', label: 'Stok Durumu', end: true },
  { to: '/stock/ledger', label: 'Stok Hareketleri' },
  { to: '/transfers', label: 'Transferler' },
  { to: '/users', label: 'Kullanicilar', adminOnly: true },
];

export default function Sidebar() {
  const { isAdmin } = useAuth();
  const visible = links.filter((link) => !link.adminOnly || isAdmin);

  return (
    <aside className="w-28 sm:w-44 md:w-56 bg-indigo-900 text-indigo-100 shrink-0 p-2 sm:p-4">
      <nav className="flex flex-col gap-1">
        {visible.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            data-testid={`nav-${link.label.toLowerCase()}`}
            className={({ isActive }) =>
              `px-2 sm:px-3 py-2 rounded text-xs sm:text-sm transition-colors ${
                isActive
                  ? 'bg-indigo-700 text-white font-medium'
                  : 'hover:bg-indigo-800 text-indigo-200'
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
