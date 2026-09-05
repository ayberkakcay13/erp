// Sayfalarda tekrar tekrar kullanilan kucuk gorsel parcalar.

export function PageHeader({ title, children }) {
  return (
    <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
      <h2 className="text-xl font-semibold text-gray-800">{title}</h2>
      <div className="flex gap-2">{children}</div>
    </div>
  );
}

export function Loading({ label = 'Yukleniyor...' }) {
  return (
    <div data-testid="loading" className="flex items-center gap-2 text-gray-500 py-8">
      <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-indigo-600 rounded-full animate-spin" />
      {label}
    </div>
  );
}

export function ErrorMessage({ message, onRetry }) {
  if (!message) return null;
  return (
    <div
      data-testid="error"
      className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 mb-4 text-sm flex items-start justify-between gap-3"
    >
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="underline shrink-0 hover:text-red-900">
          Tekrar dene
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message }) {
  return (
    <div data-testid="empty" className="text-gray-500 text-sm py-8 text-center">
      {message}
    </div>
  );
}

export function Button({ variant = 'primary', className = '', ...props }) {
  const styles = {
    primary: 'bg-indigo-600 hover:bg-indigo-700 text-white',
    secondary: 'bg-white hover:bg-gray-50 text-gray-700 border border-gray-300',
    danger: 'bg-red-600 hover:bg-red-700 text-white',
  };
  return (
    <button
      {...props}
      className={`px-3 py-1.5 rounded text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${styles[variant]} ${className}`}
    />
  );
}

export function Field({ label, error, children }) {
  return (
    <label className="block mb-3">
      <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>
      {children}
      {error && <span className="block text-xs text-red-600 mt-1">{error}</span>}
    </label>
  );
}

export const inputClass =
  'w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500';

export function Badge({ children, tone = 'gray' }) {
  const tones = {
    gray: 'bg-gray-100 text-gray-700',
    green: 'bg-green-100 text-green-700',
    yellow: 'bg-yellow-100 text-yellow-800',
    red: 'bg-red-100 text-red-700',
    blue: 'bg-blue-100 text-blue-700',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function formatMoney(value) {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    minimumFractionDigits: 2,
  }).format(Number(value ?? 0));
}

export function formatDate(value) {
  if (!value) return '-';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleDateString('tr-TR');
}
