import { Button, inputClass } from './ui';

/**
 * Listelerin ustundeki arama/filtre seridi. Sonuc sayisini ve
 * "Filtreleri Temizle" butonunu tek yerde tutar.
 */
export default function FilterBar({
  children,
  resultCount,
  totalCount,
  onClear,
  hasFilters,
  testid = 'filter-bar',
}) {
  return (
    <div
      data-testid={testid}
      className="bg-white border border-gray-200 rounded p-3 mb-4 flex flex-wrap items-end gap-3"
    >
      {children}

      <div className="ml-auto flex items-center gap-3">
        <span className="text-sm text-gray-500" data-testid="result-count">
          {hasFilters ? `${resultCount} sonuc` : `${totalCount} kayit`}
          {hasFilters && totalCount !== resultCount && (
            <span className="text-gray-400"> / {totalCount}</span>
          )}
        </span>
        {hasFilters && (
          <Button variant="secondary" onClick={onClear} data-testid="clear-filters">
            Filtreleri Temizle
          </Button>
        )}
      </div>
    </div>
  );
}

export function FilterField({ label, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-xs font-medium text-gray-600 mb-1">{label}</span>
      {children}
    </label>
  );
}

export function SearchInput({ value, onChange, placeholder, testid }) {
  return (
    <input
      type="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      data-testid={testid}
      className={`${inputClass} min-w-[200px]`}
    />
  );
}

export function SelectFilter({ value, onChange, options, testid }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      data-testid={testid}
      className={inputClass}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** Tiklanabilir tablo basligi (siralama icin) */
export function SortableTh({ label, sortKey, sort, onSort, align = 'left', testid }) {
  return (
    <th
      className={`px-4 py-2 font-medium cursor-pointer select-none hover:text-indigo-700 text-${align}`}
      onClick={() => onSort(sortKey)}
      data-testid={testid ?? `sort-${sortKey}`}
    >
      {label}
      <span className="text-indigo-600">
        {sort?.key === sortKey ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
      </span>
    </th>
  );
}
