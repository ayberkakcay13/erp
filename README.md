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
🚀 Phase 12 tamamlandı — aktif geliştirme
