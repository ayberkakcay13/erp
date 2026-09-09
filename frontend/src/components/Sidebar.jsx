import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Phase 12: `module` alani olan baglantilar, o modul kapaliysa menude cikmaz
// Phase 14: `group` alani menuyu Satis / Satin Alma / Stok basliklarina boler
const links = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/customers', label: 'Musteriler' },
  { to: '/products', label: 'Urunler' },
  { to: '/catalog', label: 'Katalog', adminOnly: true },
  { to: '/sales', label: 'Satislar', module: 'sales', group: 'Satis' },
  { to: '/invoices', label: 'Faturalar', module: 'invoice', group: 'Satis' },
  { to: '/suppliers', label: 'Tedarikciler', module: 'purchase', group: 'Satin Alma' },
  {
    to: '/purchase/orders',
    label: 'Siparisler',
    module: 'purchase',
    group: 'Satin Alma',
  },
  {
    to: '/purchase/receipts',
    label: 'Mal Kabul',
    module: 'purchase',
    group: 'Satin Alma',
  },
  {
    to: '/purchase/invoices',
    label: 'Alis Faturalari',
    module: 'purchase',
    group: 'Satin Alma',
  },
  { to: '/stock', label: 'Stok Durumu', end: true, module: 'stock', group: 'Stok' },
  { to: '/stock/ledger', label: 'Stok Hareketleri', module: 'stock', group: 'Stok' },
  { to: '/transfers', label: 'Transferler', module: 'stock', group: 'Stok' },
  { to: '/users', label: 'Kullanicilar', adminOnly: true },
  { to: '/audit-log', label: 'Denetim Izi', adminOnly: true },
  { to: '/tenants', label: 'Firmalar', superadminOnly: true },
];

const linkClass = ({ isActive }) =>
  `px-2 sm:px-3 py-2 rounded text-xs sm:text-sm transition-colors ${
    isActive
      ? 'bg-indigo-700 text-white font-medium'
      : 'hover:bg-indigo-800 text-indigo-200'
  }`;

/** Ardisik ayni gruptaki baglantilari tek bolume toplar. */
function toSections(items) {
  const sections = [];
  for (const link of items) {
    const group = link.group ?? null;
    const last = sections[sections.length - 1];
    if (last && last.group === group) {
      last.links.push(link);
    } else {
      sections.push({ group, links: [link] });
    }
  }
  return sections;
}

export default function Sidebar() {
  const { isAdmin, isSuperadmin, hasModule } = useAuth();
  const visible = links.filter(
    (link) =>
      (!link.adminOnly || isAdmin)
      && (!link.superadminOnly || isSuperadmin)
      && (!link.module || hasModule(link.module))
  );

  return (
    <aside className="w-28 sm:w-44 md:w-56 bg-indigo-900 text-indigo-100 shrink-0 p-2 sm:p-4 overflow-y-auto">
      <nav className="flex flex-col gap-1">
        {toSections(visible).map((section) => (
          <div key={section.group ?? 'genel'} className="flex flex-col gap-1">
            {section.group && (
              <div className="px-2 sm:px-3 pt-3 pb-1 text-[10px] sm:text-xs uppercase tracking-wide text-indigo-400">
                {section.group}
              </div>
            )}
            {section.links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                data-testid={`nav-${link.label.toLowerCase()}`}
                className={linkClass}
              >
                {link.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
