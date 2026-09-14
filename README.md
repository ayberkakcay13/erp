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
- ✅ **Satış zinciri: teklif → satış siparişi → irsaliye → fatura** (Phase 15)
- ✅ **Dashboard: satış trendi grafiği, son satışlar/siparişler tablosu** (Phase 16)
- ✅ **Müşteri/ürün detay pencereleri (3 sekme: siparişler + satış trendi)** (Phase 17)
- ✅ **Detay pencereleri backend'e bağlandı + test kapsamı genişletildi** (Phase 18)
- ✅ **Mock veri → gerçek `sales_orders` sorgusuna geçiş (production-ready API)** (Phase 19)

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

Ledger satırına `unit_cost` (stok birimi başına maliyet) yazılır; ileride
eklenecek stok değerlemesi (FIFO / hareketli ortalama) buna dayanacak.

### Satış zinciri refactoring (Phase 15)
Eski `sales`/`sales_items` tabloları `sales_orders`/`sales_order_items` olarak
yeniden adlandırıldı (id'ler korunarak — `stock_ledger_entries` ve
`audit_logs` bu id'lere referans veriyor). `app/models.py` içinde
`Sale = SalesOrder`, `SalesItem = SalesOrderItem` **Python alias'ları** vardır;
ayrı tablo değildir, yalnızca Phase 10-14 kodunun eski isimlerle çalışmaya
devam etmesi içindir. `routers/sales.py` (`/api/sales`) geriye uyum katmanı,
yeni geliştirme `routers/sales_orders.py` + `quotations.py` +
`delivery_notes.py` üzerinden yapılır.

### Dashboard + detay pencereleri (Phase 16-19)
Dashboard'daki satış trendi grafiği (4 zaman aralığı + tarih navigasyonu) ve
Müşteriler/Ürünler sayfalarındaki satır tıklamasıyla açılan detay pencereleri
(Devam Eden Siparişler / Son Siparişler / Satış Trendi sekmeleri) **mock veriyle**
başladı (Phase 16-17), Phase 18'de mock veri backend'e taşındı
(`app/mocks/`), Phase 19'da bu katman **kaldırılıp gerçek `sales_orders` /
`sales_order_items` sorgularıyla** değiştirildi:

- `GET /api/customers/{id}/orders`, `/api/customers/{id}/sales-trend`
- `GET /api/products/{id}/orders`, `/api/products/{id}/sales-trend`
- `GET /api/sales/trend`, `/api/sales/recent`, `/api/sales/recent-orders`

Sorgu mantığı `app/services/sales_query_service.py`'de toplanır ve **mevcut
SQLAlchemy `Session`** (`get_db()`) üzerinden çalışır — repo'da supabase-py/REST
client yok, tenant izolasyonu (Phase 12) zaten bu session'a bağlı
`SET LOCAL ROLE erp_app` + RLS ile sağlanıyor; ayrı bir Supabase client bu
izolasyonu bypass ederdi.

Önemli tasarım kararları:
- **Teslimat tarihi** kaynağı `SalesOrder.promised_delivery_date` (planlanan
  teslimat) — yeni bir kolon eklenmedi, mevcut alan yeniden kullanıldı.
- Bir sipariş birden çok ürün satırı (`SalesOrderItem`) içerebilir: müşteri
  modalında **sipariş başına 1 satır** (ürün kolonu "ilk ürün + N urun"),
  ürün modalında **kalem başına 1 satır** (tutar o kalemin satır toplamı).
- Gerçek `SalesOrder.status` değerleri (`draft/pending/confirmed/
  partially_delivered/delivered/completed/cancelled`) UI'nin üç durumlu
  (pending/processing/delivered) rozet sistemine `sales_query_service._STATUS_MAP`
  ile eşlenir; `cancelled` siparişler sipariş listelerinden tamamen hariç
  tutulur (asıl mock tasarımıyla aynı davranış).
- `customer_id`/`sale_date` (sales_orders) ve `product_id`/`sales_order_id`
  (sales_order_items) için indeks eklendi (`migrate_phase19_indexes.py`,
  idempotent) — bu sorgular artık sık çalışıyor.

Frontend tarafında `frontend/src/hooks/` altında `useCustomerOrders`,
`useProductOrders`, `useSalesTrend` hook'ları eklendi; bunlar **çıplak
`fetch()` kullanmaz**, mevcut `services/api.js` (axios, Bearer token + hata
normalizasyonu) üzerinden geçer.

⚠️ `/api/sales/trend`, `/api/sales/recent`, `/api/sales/recent-orders` aynı
router'daki `/api/sales/{sale_id}`'den **önce** tanımlıdır — aksi halde
FastAPI bu sabit yolları `sale_id` path parametresi sanıp 422 döner.

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
env\Scripts\python.exe migrate_phase15_sales.py       # Phase 15
env\Scripts\python.exe migrate_phase19_indexes.py     # Phase 19 (indeks, tablo eklemez)
```

Phase 16-18 yeni tablo/migration eklemedi. Phase 19 de yeni tablo eklemedi —
sadece mevcut `sales_orders`/`sales_order_items` üzerine indeks ekledi; şema
zaten Phase 15'ten beri yeterliydi (Notion Phase 19 spec'i "sales_orders/
customers/products tabloları oluştur" diyordu, ama bunlar Phase 10-15'te
zaten mevcuttu — kontrol edildi, eksik tablo yoktu).

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
env\Scripts\python.exe -m pytest --cov=app tests/  # coverage raporu
env\Scripts\python.exe tests/full_flow_test.py  # uçtan uca (sunucu açıkken)
```

```bash
cd frontend
npm test -- --watchAll=false   # Jest + React Testing Library
```

Backend testleri gerçek Supabase veritabanına karşı koşar ve oluşturdukları her
kaydı temizler — production tablolarında test verisi bırakmazlar. Phase 19'da
`/api/customers/{id}/orders` gibi endpoint'ler artık gerçek veri döndürdüğü
için testleri de gerçek `client`+`tracker` deseniyle kendi müşteri/ürün/
siparişini oluşturup doğrular (Phase 18'in "mock veri hep dolu döner"
varsayımına dayanan testleri kaldırıldı).

API dokümantasyonu ayrıca yazılmadı — FastAPI zaten `uvicorn` çalışırken
`/docs` (Swagger UI) ve `/openapi.json`'ı otomatik üretir.

## Durum
🚀 Phase 19 tamamlandı — aktif geliştirme
