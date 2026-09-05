/**
 * Arama/filtreleme yardimcilari.
 *
 * Turkce karakter notu: "cag" yazinca "Cagla" bulunmali. Bunun icin once
 * Turkce yerel ayariyla kucuk harfe cevirip (I -> i sorunu), sonra aksanlari
 * kaldiriyoruz. Boylece hem "cag" hem "cag" ayni sonucu veriyor.
 */

const TR_MAP = {
  ç: 'c', Ç: 'c', ğ: 'g', Ğ: 'g', ı: 'i', İ: 'i',
  ö: 'o', Ö: 'o', ş: 's', Ş: 's', ü: 'u', Ü: 'u', â: 'a', î: 'i', û: 'u',
};

export function normalize(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .toLocaleLowerCase('tr')
    .replace(/[çÇğĞıİöÖşŞüÜâîû]/g, (ch) => TR_MAP[ch] ?? ch);
}

/** Aranan metin, verilen alanlardan herhangi birinde geciyor mu? */
export function matches(item, fields, query) {
  const q = normalize(query).trim();
  if (!q) return true;
  return fields.some((f) => normalize(item[f]).includes(q));
}

/** Turkce siralama (A-Z'de C, G, I, O, S, U dogru yere gelir) */
export function compareText(a, b) {
  return String(a ?? '').localeCompare(String(b ?? ''), 'tr', { sensitivity: 'base' });
}

export function compareNumber(a, b) {
  return Number(a ?? 0) - Number(b ?? 0);
}

/**
 * Bir listeyi siralar. sort = { key, dir } ; dir: 'asc' | 'desc'
 * numericKeys icindeki alanlar sayisal, digerleri metin olarak karsilastirilir.
 */
export function sortRows(rows, sort, numericKeys = []) {
  if (!sort?.key) return rows;
  const cmp = numericKeys.includes(sort.key) ? compareNumber : compareText;
  const sorted = [...rows].sort((a, b) => cmp(a[sort.key], b[sort.key]));
  return sort.dir === 'desc' ? sorted.reverse() : sorted;
}

/** Baslik tiklamasinda siralamayi degistirir (ayni sutun -> yon degisir) */
export function toggleSort(current, key) {
  if (current?.key !== key) return { key, dir: 'asc' };
  if (current.dir === 'asc') return { key, dir: 'desc' };
  return { key: null, dir: 'asc' }; // ucuncu tiklamada siralama kalkar
}

export function sortIcon(sort, key) {
  if (sort?.key !== key) return '';
  return sort.dir === 'asc' ? ' ▲' : ' ▼';
}

/** Tarih araligi kontrolu (ISO tarih metinleri ile calisir) */
export function inDateRange(value, start, end) {
  if (!value) return !start && !end;
  const v = String(value).slice(0, 10);
  if (start && v < start) return false;
  if (end && v > end) return false;
  return true;
}
