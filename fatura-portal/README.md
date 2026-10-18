# Fatura Portalı

GİB e-Arşiv Portal'a bağlanıp fatura kesen yerel uygulama. Node 18+ gerekir, ek paket yok.

- **Deneme (gerçek fatura kesmez):** `baslat-deneme.bat` — SMS kodu `123456`.
- **Gerçek:** `baslat.bat` (ya da `node server.js`) → http://127.0.0.1:3000
- Veriler `data/kasa.json` dosyasında, uygulama şifresiyle AES-256-GCM şifreli (GİB şifreleri dahil). Bu klasör git'e girmez.
- Fatura 3 adımda kesilir: taslak → SMS kodu → onay. Taslak GİB portalının "Taslak Faturalar" listesinde görünür.
- `gib.js` içinde "DOĞRULANACAK" yazan alanlar (tevkifat tipi ve toplam alanları) gerçek portalda ilk taslakla kontrol edilmelidir.
- Telefon için: aynı uygulama bir sunucuda `HOST=0.0.0.0` ile çalıştırılır (HTTPS arkasında).
