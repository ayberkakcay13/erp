import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Phase 12: `module` alani olan baglantilar, o modul kapaliysa menude cikmaz
const links = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/customers', label: 'Musteriler' },
  { to: '/products', label: 'Urunler' },
  { to: '/catalog', label: 'Katalog', adminOnly: true },
  { to: '/sales', label: 'Satislar', module: 'sales' },
  { to: '/invoices', label: 'Faturalar', module: 'invoice' },
  { to: '/stock', label: 'Stok Durumu', end: true, module: 'stock' },
  { to: '/stock/ledger', label: 'Stok Hareketleri', module: 'stock' },
  { to: '/transfers', label: 'Transferler', module: 'stock' },
  { to: '/users', label: 'Kullanicilar', adminOnly: true },
  { to: '/audit-log', label: 'Denetim Izi', adminOnly: true },
  { to: '/tenants', label: 'Firmalar', superadminOnly: true },
];

export default function Sidebar() {
  const { isAdmin, isSuperadmin, hasModule } = useAuth();
  const visible = links.filter(
    (link) =>
      (!link.adminOnly || isAdmin)
      && (!link.superadminOnly || isSuperadmin)
      && (!link.module || hasModule(link.module))
  );

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
