# ERP System

FastAPI + React + Supabase ile çok kiracılı (multi-tenant) ERP sistemi.

## Tech Stack
- Frontend: React + Tailwind CSS
- Backend: FastAPI + SQLAlchemy
- Database: Supabase (PostgreSQL, Transaction Pooler / 6543)

## Özellikler
- ✅ Müşteri yönetimi (CRUD)
- ✅ Ürün kataloğu
- ✅ Satış yönetimi
- ✅ Fatura oluşturma + PDF
- ✅ Raporlar, uyarılar, arama/filtreleme
- ✅ **Stok defteri ve depo yönetimi** (Phase 10)
- ✅ **Belge durumu, numaralandırma, denetim izi** (Phase 11)
- ✅ **Çok kiracılı mimari + PostgreSQL RLS** (Phase 12)
- ✅ **Ölçü birimi, kategori, marka, barkod, varyant** (Phase 13)
- ✅ **Tedarikçi ve satın alma: sipariş → mal kabul → alış faturası** (Phase 14)

## Mimari notlar

### Stok defteri (Phase 10)
Stok `products` tablosunda bir sayı değil, muhasebe defteri mantığıyla tutulur:
her hareket bir satır (`stock_ledger_entries`), güncel stok satırların toplamı.
Ledger satırları **asla** UPDATE/DELETE edilmez; düzeltme ters kayıtla yapılır.
Tüm stok işlemleri `app/services/stock_service.py` üzerinden geçer.

### Belge yaşam döngüsü (Phase 11)
`status` iş akışıdır (bekliyor/tamamlandı), `docstatus` belge durumudur
(0 taslak / 1 onaylı / 2 iptal) — ikisi ayrı kavram. Onaylanmış belge
değiştirilemez, iptal edilen belge tekrar onaylanamaz. Numaralar
(`FT-2026-00001`) onay anında, atomik sayaçtan atanır.

### Çok kiracılılık (Phase 12)
İzolasyon satır bazlı `tenant_id` + PostgreSQL Row Level Security ile sağlanır.
Uygulama katmanında `WHERE tenant_id = ?` unutulsa bile veritabanı satırı
döndürmez.

⚠️ **Supabase'e özgü iki tuzak ve çözümleri:**

1. **`postgres` rolü `BYPASSRLS` ayrıcalığı taşır.** Bu ayrıcalık RLS'i
   tamamen atlar; `ENABLE` ve `FORCE ROW LEVEL SECURITY` bile bir şey
   değiştirmez. Bu yüzden migration ayrıcalıksız bir `erp_app` rolü açar ve
   uygulama her transaction başında `SET LOCAL ROLE erp_app` ile ona geçer
   (`app/services/tenant_context.py`). Bağlantı bilgileri değişmez.
2. **Oturum düzeyi `set_config(..., false)` havuza sızar.** Transaction Pooler
   bağlantıyı geri verdiğinde ayar üzerinde kalır. Tüm tenant/bypass ayarları
   transaction düzeyindedir (`set_config(..., true)` = `SET LOCAL`).
   `tests/test_phase12_tenant.py::test_pooler_set_local_sizmiyor` bunu ardışık
   ve eş zamanlı erişimle doğrular.

### Ürün yapısı (Phase 13)
Ürün kartı ölçü birimi (`stock_uom` / `purchase_uom` / `sales_uom`), kategori
ağacı (`item_groups`), marka, barkod ve varyant taşır.

**Değişmez kural:** stok defterine yazılan miktar **her zaman ürünün stok
biriminde**dir. Koli alınıp adet satılabilir; dönüşüm ledger'a yazılmadan önce
`app/services/uom_service.py` içinde yapılır. Satış kaleminde `quantity`
müşterinin girdiği birimde (fiyat da o birimde), `stock_quantity` ise stok
birimine çevrilmiş halidir — ledger `stock_quantity` kullanır.

Varyant şablonu ("Tişört") stok tutmaz; stok varyantlarda ("Tişört-Kırmızı-M")
durur. Hizmet ürünü de stok tutmaz. İkisi de
`product_service.ensure_not_template()` ile `stock_service.add_entry()`
içinden engellenir.

### Satın alma zinciri (Phase 14)
Alım → stok → satış döngüsü bu fazda kapandı.

**Hangi belge stok hareketi yaratır? Sadece mal kabul.** Sipariş niyet
beyanıdır, alış faturası mali belgedir — ikisi de ledger'a dokunmaz. Bu ayrım
ERP'nin temelidir.

Mal kabul onaylandığında miktar `uom_service` ile ürünün stok birimine
çevrilip `stock_service.add_entry(reason='alim', ref_type='purchase')` ile
yazılır; iptalde `alim_iade` ters kaydı düşer. Aynı anda sipariş kaleminin
`received_quantity` alanı güncellenir ve sipariş durumu (`beklemede` /
`kismi_teslim` / `tamamlandi`) yeniden hesaplanır — bu alan senkron kalmazsa
kısmi teslim hesabı bozulur.

Ledger satırına `unit_cost` (stok birimi başına maliyet) yazılır; Phase 16'daki
stok değerlemesi (FIFO / hareketli ortalama) buna dayanacak.

## Kurulum

### Backend
```bash
cd backend
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Migration'lar (sırayla, hepsi idempotent)
```bash
cd backend
env\Scripts\python.exe migrate_stock_to_ledger.py     # Phase 10
env\Scripts\python.exe migrate_phase11_documents.py   # Phase 11
env\Scripts\python.exe migrate_phase12_tenant.py      # Phase 12
env\Scripts\python.exe migrate_phase13_catalog.py     # Phase 13
env\Scripts\python.exe migrate_phase14_purchase.py    # Phase 14
```

### Frontend
```bash
cd frontend
npm install
npm start
```

## Testler

```bash
cd backend
env\Scripts\python.exe -m pytest              # faz testleri (pytest)
env\Scripts\python.exe tests/full_flow_test.py  # uçtan uca (sunucu açıkken)
```

Testler gerçek Supabase veritabanına karşı koşar ve oluşturdukları her kaydı
temizler — production tablolarında test verisi bırakmazlar.

## Durum
🚀 Phase 14 tamamlandı — aktif geliştirme
