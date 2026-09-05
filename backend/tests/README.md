# Testler

## full_flow_test.py

Ucdan uca senaryo: customer -> 3 product -> sale (2 urun) -> invoice -> status paid.
Calisan bir sunucuya HTTP istegi atar, bu yuzden once sunucuyu baslat.

```powershell
# 1. terminal
cd backend
.\env\Scripts\Activate.ps1
uvicorn app.main:app --reload

# 2. terminal
cd backend
.\env\Scripts\python.exe tests\full_flow_test.py
```

Basarisiz kontrol varsa script exit code 1 ile biter.
