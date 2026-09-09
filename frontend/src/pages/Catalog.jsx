import { useCallback, useEffect, useState } from 'react';
import {
  Badge,
  Button,
  EmptyState,
  ErrorMessage,
  Field,
  Loading,
  PageHeader,
  formatQty,
  inputClass,
} from '../components/ui';
import {
  attributeAPI,
  brandAPI,
  conversionAPI,
  itemGroupAPI,
  uomAPI,
} from '../services/api';

/** Kategori agacini girintili gosterir. */
function GroupTree({ nodes, depth = 0, onDelete, busy }) {
  return (
    <ul className={depth === 0 ? 'divide-y divide-gray-100' : ''}>
      {nodes.map((node) => (
        <li key={node.id}>
          <div
            className="flex items-center gap-2 px-3 py-1.5"
            style={{ paddingLeft: `${12 + depth * 20}px` }}
            data-testid={`group-${node.id}`}
          >
            {depth > 0 && <span className="text-gray-300">└</span>}
            <span className="text-gray-800">{node.name}</span>
            <span className="font-mono text-xs text-gray-400">{node.code}</span>
            {!node.is_active && <Badge tone="gray">Pasif</Badge>}
            <button
              type="button"
              disabled={busy}
              onClick={() => onDelete(node)}
              className="ml-auto text-xs text-red-600 hover:underline"
              data-testid={`delete-group-${node.id}`}
            >
              Sil
            </button>
          </div>
          {node.children?.length > 0 && (
            <GroupTree
              nodes={node.children}
              depth={depth + 1}
              onDelete={onDelete}
              busy={busy}
            />
          )}
        </li>
      ))}
    </ul>
  );
}

function Section({ title, children, action }) {
  return (
    <section className="bg-white border border-gray-200 rounded mb-5">
      <div className="border-b border-gray-100 px-4 py-2 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">{title}</h3>
        <div className="ml-auto">{action}</div>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Urun yapisi yonetimi (Phase 13): birimler, donusumler, kategori, marka, oznitelik. */
export default function Catalog() {
  const [uoms, setUoms] = useState([]);
  const [conversions, setConversions] = useState([]);
  const [tree, setTree] = useState([]);
  const [groups, setGroups] = useState([]);
  const [brands, setBrands] = useState([]);
  const [attributes, setAttributes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [groupForm, setGroupForm] = useState({ code: '', name: '', parent_id: '' });
  const [brandName, setBrandName] = useState('');
  const [conversionForm, setConversionForm] = useState({
    from_uom_id: '', to_uom_id: '', factor: '',
  });
  const [attributeForm, setAttributeForm] = useState({ name: '', values: '' });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [u, c, t, g, b, a] = await Promise.all([
        uomAPI.getAll(),
        conversionAPI.getAll(),
        itemGroupAPI.tree(),
        itemGroupAPI.getAll(),
        brandAPI.getAll(),
        attributeAPI.getAll(),
      ]);
      setUoms(u);
      setConversions(c);
      setTree(t);
      setGroups(g);
      setBrands(b);
      setAttributes(a);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (action, message) => {
    setBusy(true);
    setError('');
    try {
      await action();
      setNotice(message);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Loading />;

  return (
    <div data-testid="page-Catalog">
      <PageHeader title="Urun Yapisi">
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => run(uomAPI.ensureDefaults, 'Varsayilan birimler kuruldu.')}
          data-testid="ensure-uoms"
        >
          Varsayilan birimleri kur
        </Button>
      </PageHeader>

      <ErrorMessage message={error} onRetry={load} />
      {notice && (
        <div
          data-testid="notice"
          className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-4"
        >
          {notice}
        </div>
      )}

      <Section title="Olcu birimleri">
        {uoms.length === 0 ? (
          <EmptyState message="Henuz birim yok. 'Varsayilan birimleri kur' ile baslayin." />
        ) : (
          <div className="flex flex-wrap gap-2">
            {uoms.map((u) => (
              <span
                key={u.id}
                className="text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1"
                data-testid={`uom-${u.id}`}
              >
                {u.name} <span className="text-gray-400">({u.code})</span>
                {u.is_integer && <span className="text-gray-400"> · bolunemez</span>}
              </span>
            ))}
          </div>
        )}
      </Section>

      <Section title="Birim donusumleri">
        <form
          className="flex flex-wrap items-end gap-2 mb-3"
          onSubmit={(e) => {
            e.preventDefault();
            run(
              () => conversionAPI.create({
                from_uom_id: Number(conversionForm.from_uom_id),
                to_uom_id: Number(conversionForm.to_uom_id),
                factor: String(conversionForm.factor),
              }),
              'Donusum eklendi.'
            ).then(() => setConversionForm({ from_uom_id: '', to_uom_id: '', factor: '' }));
          }}
        >
          <Field label="1 birim">
            <select
              className={inputClass}
              value={conversionForm.from_uom_id}
              onChange={(e) =>
                setConversionForm({ ...conversionForm, from_uom_id: e.target.value })
              }
              required
              data-testid="conv-from"
            >
              <option value="">Seciniz</option>
              {uoms.map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
          </Field>
          <Field label="= kac">
            <input
              type="number"
              step="any"
              min="0"
              className={`${inputClass} w-28`}
              value={conversionForm.factor}
              onChange={(e) =>
                setConversionForm({ ...conversionForm, factor: e.target.value })
              }
              required
              data-testid="conv-factor"
            />
          </Field>
          <Field label="birim">
            <select
              className={inputClass}
              value={conversionForm.to_uom_id}
              onChange={(e) =>
                setConversionForm({ ...conversionForm, to_uom_id: e.target.value })
              }
              required
              data-testid="conv-to"
            >
              <option value="">Seciniz</option>
              {uoms.map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
          </Field>
          <Button type="submit" disabled={busy} data-testid="conv-submit">
            Ekle
          </Button>
        </form>

        {conversions.length === 0 ? (
          <EmptyState message="Tanimli donusum yok." />
        ) : (
          <ul className="text-sm divide-y divide-gray-100 border border-gray-100 rounded">
            {conversions.map((c) => (
              <li key={c.id} className="flex items-center gap-3 px-3 py-1.5">
                <span className="text-gray-700">
                  1 {c.from_uom_code} = {formatQty(c.factor)} {c.to_uom_code}
                </span>
                {c.product_id && (
                  <Badge tone="blue">urune ozel #{c.product_id}</Badge>
                )}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(() => conversionAPI.delete(c.id), 'Donusum silindi.')
                  }
                  className="ml-auto text-xs text-red-600 hover:underline"
                >
                  Sil
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Kategoriler">
        <form
          className="flex flex-wrap items-end gap-2 mb-3"
          onSubmit={(e) => {
            e.preventDefault();
            run(
              () => itemGroupAPI.create({
                code: groupForm.code,
                name: groupForm.name,
                parent_id: groupForm.parent_id ? Number(groupForm.parent_id) : null,
              }),
              'Kategori eklendi.'
            ).then(() => setGroupForm({ code: '', name: '', parent_id: '' }));
          }}
        >
          <Field label="Kod">
            <input
              className={`${inputClass} w-32`}
              value={groupForm.code}
              onChange={(e) => setGroupForm({ ...groupForm, code: e.target.value })}
              required
              data-testid="group-code"
            />
          </Field>
          <Field label="Ad">
            <input
              className={inputClass}
              value={groupForm.name}
              onChange={(e) => setGroupForm({ ...groupForm, name: e.target.value })}
              required
              data-testid="group-name"
            />
          </Field>
          <Field label="Ust kategori">
            <select
              className={inputClass}
              value={groupForm.parent_id}
              onChange={(e) => setGroupForm({ ...groupForm, parent_id: e.target.value })}
              data-testid="group-parent"
            >
              <option value="">(kok)</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </Field>
          <Button type="submit" disabled={busy} data-testid="group-submit">
            Ekle
          </Button>
        </form>

        {tree.length === 0 ? (
          <EmptyState message="Henuz kategori yok." />
        ) : (
          <div className="border border-gray-100 rounded" data-testid="group-tree">
            <GroupTree
              nodes={tree}
              busy={busy}
              onDelete={(node) =>
                run(() => itemGroupAPI.delete(node.id), `"${node.name}" silindi.`)
              }
            />
          </div>
        )}
      </Section>

      <Section title="Markalar">
        <form
          className="flex items-end gap-2 mb-3"
          onSubmit={(e) => {
            e.preventDefault();
            run(() => brandAPI.create({ name: brandName }), 'Marka eklendi.')
              .then(() => setBrandName(''));
          }}
        >
          <Field label="Marka adi">
            <input
              className={inputClass}
              value={brandName}
              onChange={(e) => setBrandName(e.target.value)}
              required
              data-testid="brand-name"
            />
          </Field>
          <Button type="submit" disabled={busy} data-testid="brand-submit">
            Ekle
          </Button>
        </form>

        {brands.length === 0 ? (
          <EmptyState message="Henuz marka yok." />
        ) : (
          <div className="flex flex-wrap gap-2">
            {brands.map((b) => (
              <span
                key={b.id}
                className="text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1 flex items-center gap-2"
                data-testid={`brand-${b.id}`}
              >
                {b.name}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => run(() => brandAPI.delete(b.id), 'Marka silindi.')}
                  className="text-red-600 hover:underline"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </Section>

      <Section title="Varyant oznitelikleri">
        <form
          className="flex flex-wrap items-end gap-2 mb-3"
          onSubmit={(e) => {
            e.preventDefault();
            const values = attributeForm.values
              .split(',')
              .map((v) => v.trim())
              .filter(Boolean)
              .map((value, index) => ({ value, sort_order: index }));
            run(
              () => attributeAPI.create({ name: attributeForm.name, values }),
              'Oznitelik eklendi.'
            ).then(() => setAttributeForm({ name: '', values: '' }));
          }}
        >
          <Field label="Oznitelik (Renk, Beden)">
            <input
              className={inputClass}
              value={attributeForm.name}
              onChange={(e) =>
                setAttributeForm({ ...attributeForm, name: e.target.value })
              }
              required
              data-testid="attribute-name"
            />
          </Field>
          <Field label="Degerler (virgulle)">
            <input
              className={`${inputClass} w-64`}
              value={attributeForm.values}
              onChange={(e) =>
                setAttributeForm({ ...attributeForm, values: e.target.value })
              }
              placeholder="Kirmizi, Mavi, Yesil"
              data-testid="attribute-values"
            />
          </Field>
          <Button type="submit" disabled={busy} data-testid="attribute-submit">
            Ekle
          </Button>
        </form>

        {attributes.length === 0 ? (
          <EmptyState message="Henuz oznitelik yok." />
        ) : (
          <ul className="text-sm divide-y divide-gray-100 border border-gray-100 rounded">
            {attributes.map((a) => (
              <li
                key={a.id}
                className="flex items-center gap-3 px-3 py-1.5"
                data-testid={`attribute-${a.id}`}
              >
                <span className="text-gray-800 font-medium">{a.name}</span>
                <span className="text-gray-500 text-xs">
                  {a.values.map((v) => v.value).join(' · ')}
                </span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(() => attributeAPI.delete(a.id), `"${a.name}" silindi.`)
                  }
                  className="ml-auto text-xs text-red-600 hover:underline"
                >
                  Sil
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
