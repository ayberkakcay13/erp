import { useState } from 'react';
import { Badge, Button, inputClass } from './ui';

/**
 * Phase 11: belge yasam dongusu (docstatus) arayuz parcalari.
 *
 * `status` (is akisi: bekliyor / tamamlandi) ile `docstatus` (belge durumu:
 * taslak / onayli / iptal) ayri kavramlar - ikisi ayri rozetle gosterilir.
 */

export const DOC_DRAFT = 0;
export const DOC_SUBMITTED = 1;
export const DOC_CANCELLED = 2;

export const docStatusLabel = {
  [DOC_DRAFT]: 'Taslak',
  [DOC_SUBMITTED]: 'Onayli',
  [DOC_CANCELLED]: 'Iptal',
};

const docStatusTone = {
  [DOC_DRAFT]: 'gray',
  [DOC_SUBMITTED]: 'green',
  [DOC_CANCELLED]: 'red',
};

export const isDraft = (doc) => (doc?.docstatus ?? DOC_DRAFT) === DOC_DRAFT;
export const isSubmitted = (doc) => doc?.docstatus === DOC_SUBMITTED;
export const isCancelled = (doc) => doc?.docstatus === DOC_CANCELLED;

export function DocStatusBadge({ docstatus, testid }) {
  const value = docstatus ?? DOC_DRAFT;
  return (
    <Badge tone={docStatusTone[value] ?? 'gray'}>
      <span data-testid={testid}>{docStatusLabel[value] ?? value}</span>
    </Badge>
  );
}

/**
 * Onayla / Iptal Et butonlari.
 * - Taslak: "Onayla" (geri donusu olmadigi uyarisiyla)
 * - Onayli: "Iptal Et" (sebep sorulur)
 * - Iptal: islem yok, belge kilitli
 */
export function DocumentActions({ doc, onSubmit, onCancel, busy, testidPrefix = 'doc' }) {
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState('');

  if (isCancelled(doc)) {
    return (
      <div className="text-sm text-gray-500" data-testid={`${testidPrefix}-locked`}>
        Bu belge iptal edilmis ve kilitli. Duzeltme icin yeni bir belge olusturun.
        {doc.cancel_reason && (
          <div className="text-xs text-gray-400 mt-1">Sebep: {doc.cancel_reason}</div>
        )}
      </div>
    );
  }

  if (isDraft(doc)) {
    return (
      <Button
        onClick={() => {
          const ok = window.confirm(
            'Belge onaylanacak. Onayladiktan sonra degistiremezsiniz; '
            + 'duzeltme icin iptal edip yenisini olusturmaniz gerekir.\n\nDevam edilsin mi?'
          );
          if (ok) onSubmit();
        }}
        disabled={busy}
        data-testid={`${testidPrefix}-submit`}
      >
        {busy ? 'Onaylaniyor...' : 'Onayla'}
      </Button>
    );
  }

  if (!cancelling) {
    return (
      <Button
        variant="danger"
        onClick={() => setCancelling(true)}
        disabled={busy}
        data-testid={`${testidPrefix}-cancel`}
      >
        Iptal Et
      </Button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid={`${testidPrefix}-cancel-form`}>
      <input
        className={`${inputClass} w-56`}
        placeholder="Iptal sebebi"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        data-testid={`${testidPrefix}-cancel-reason`}
      />
      <Button
        variant="danger"
        disabled={busy}
        onClick={() => {
          onCancel(reason || null);
          setCancelling(false);
          setReason('');
        }}
        data-testid={`${testidPrefix}-cancel-confirm`}
      >
        {busy ? 'Iptal ediliyor...' : 'Iptali Onayla'}
      </Button>
      <Button variant="secondary" onClick={() => setCancelling(false)} disabled={busy}>
        Vazgec
      </Button>
    </div>
  );
}
