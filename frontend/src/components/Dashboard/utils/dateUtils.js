// Phase 16: Dashboard tarih yardimcilari.
// Not: para formati icin components/ui.jsx icindeki formatMoney kullanilir,
// burada tekrar tanimlanmaz.

export const MONTH_NAMES = [
  'Ocak', 'Subat', 'Mart', 'Nisan', 'Mayis', 'Haziran',
  'Temmuz', 'Agustos', 'Eylul', 'Ekim', 'Kasim', 'Aralik',
];

export const MONTH_SHORT = [
  'Oca', 'Sub', 'Mar', 'Nis', 'May', 'Haz',
  'Tem', 'Agu', 'Eyl', 'Eki', 'Kas', 'Ara',
];

/** 0-index ay numarasindan ay adi (orn: 8 -> "Eylul") */
export function getMonthName(monthNumber) {
  return MONTH_NAMES[monthNumber] ?? '';
}

const pad = (n) => String(n).padStart(2, '0');

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * "YYYY-MM-DD" bicimini yerel saatte ayristirir (new Date(str) bunu UTC gece
 * yarisi kabul eder; negatif UTC offset'li makinelerde bir gun geri kayar).
 * Diger girdilerde new Date(value)'a duser.
 */
export function parseISODate(value) {
  if (typeof value === 'string' && ISO_DATE_RE.test(value)) {
    const [y, m, d] = value.split('-').map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(value);
}

/**
 * Tarihi verilen kalibla formatlar. Desteklenen: dd, MM, yyyy, yy, MMM, MMMM
 * Orn: formatDate(new Date(2026, 8, 10)) -> "10.09.2026"
 */
export function formatDate(date, format = 'dd.MM.yyyy') {
  const d = date instanceof Date ? date : parseISODate(date);
  if (Number.isNaN(d.getTime())) return '-';
  return format
    .replace('yyyy', String(d.getFullYear()))
    .replace('MMMM', MONTH_NAMES[d.getMonth()])
    .replace('MMM', MONTH_SHORT[d.getMonth()])
    .replace('MM', pad(d.getMonth() + 1))
    .replace('dd', pad(d.getDate()))
    .replace('yy', String(d.getFullYear()).slice(-2));
}

/**
 * Tarihe n ay ekler (negatif deger cikarir).
 * Gun 1'e sabitlenir; 31 Ocak + 1 ay -> 3 Mart gibi tasmalari onler.
 */
export function addMonths(date, n) {
  return new Date(date.getFullYear(), date.getMonth() + n, 1);
}

/** Tarihe n yil ekler (negatif deger cikarir) */
export function addYears(date, n) {
  return new Date(date.getFullYear() + n, date.getMonth(), 1);
}

/** Tarih navigasyonunda ortada gosterilen donem etiketi */
export function formatPeriodLabel(timeRange, date) {
  const year = date.getFullYear();
  if (timeRange === 'yearly') return String(year);
  const month = `${getMonthName(date.getMonth())} ${year}`;
  if (timeRange === 'monthly') return month;
  return `${month} - ${timeRange === 'weekly' ? 'Haftalik' : 'Gunluk'}`;
}

/** Geri/Ileri butonlarinin uzerinde yazan onceki/sonraki donem adi */
export function formatStepLabel(timeRange, date, step) {
  if (timeRange === 'yearly') return String(addYears(date, step).getFullYear());
  return getMonthName(addMonths(date, step).getMonth());
}
