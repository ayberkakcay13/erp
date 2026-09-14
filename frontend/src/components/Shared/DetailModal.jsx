import { Button } from '../ui';

/**
 * Phase 17: Detay pencereleri icin ortak kabuk.
 * Kapatma yollari: backdrop'a tiklama, sag ustteki X, alttaki Kapat butonu.
 * Desen ProductHistoryModal.jsx'ten alindi.
 */
export default function DetailModal({ title, subtitle, onClose, children, testid }) {
  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-10"
      onClick={onClose}
      data-testid={testid}
    >
      <div
        className="bg-white rounded shadow-lg max-w-4xl w-full max-h-[85vh] overflow-auto p-5 max-sm:h-full max-sm:max-h-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-gray-800 truncate">{title}</h3>
            {subtitle && <p className="text-xs text-gray-500 mt-0.5 truncate">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Kapat"
            data-testid="modal-x"
            className="text-gray-400 hover:text-gray-700 text-xl leading-none px-2 -mt-1"
          >
            &times;
          </button>
        </div>

        {children}

        <div className="mt-4 text-right">
          <Button variant="secondary" onClick={onClose} data-testid="modal-close">
            Kapat
          </Button>
        </div>
      </div>
    </div>
  );
}
