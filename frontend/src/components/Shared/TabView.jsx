/**
 * Phase 17: Tekrar kullanilabilir sekme seridi.
 * Stil ProductHistoryModal.jsx'teki tabClass deseninden alindi.
 */
export default function TabView({ tabs, active, onChange, children }) {
  const tabClass = (key) =>
    `px-3 py-1.5 text-sm rounded-t border-b-2 transition-colors ${
      active === key
        ? 'border-indigo-600 text-indigo-700 font-medium'
        : 'border-transparent text-gray-500 hover:text-gray-700'
    }`;

  return (
    <>
      <div className="flex flex-wrap gap-2 border-b border-gray-200 mb-4">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={tabClass(key)}
            onClick={() => onChange(key)}
            data-testid={`tab-${key}`}
          >
            {label}
          </button>
        ))}
      </div>
      {children}
    </>
  );
}
