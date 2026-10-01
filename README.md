# Cat Communicator PWA — Mobil Sürüm

Bu sürüm iPhone ve Android'de ana ekrana eklenebilen bir Progressive Web App (PWA)'dır.

## Telefonda ne yapar?

- Mikrofonla kedi sesi kaydı
- Mama / ilgi / oyun / kapı / selamlama / stres / bilinmiyor etiketleri
- Bağlam ve ses sonrası davranış kaydı
- Son kayıtları görüntüleme
- Ana ekrana uygulama ikonu olarak eklenebilme
- PWA manifest + service worker
- Kişisel AI modeli için veri toplama

## Yerelde çalıştırma

Python 3.11+:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Bilgisayarda:
`http://127.0.0.1:8000`

## Gerçek iPhone kurulumu

iPhone mikrofonunun sorunsuz kullanılabilmesi için uygulamayı HTTPS üzerinden yayınlamak en doğru yoldur.

Projede `render.yaml` hazırdır. GitHub'a yükleyip Render'da Blueprint/Web Service olarak deploy edebilirsin.

Deploy sonrası örnek adres:
`https://cat-communicator.onrender.com`

iPhone'da:
1. HTTPS adresini Safari ile aç.
2. Paylaş simgesine dokun.
3. "Ana Ekrana Ekle" seç.
4. Uygulama ana ekranda Cat AI ikonu ile görünür.
5. İlk ses kaydında mikrofon erişimine izin ver.

Android/Chrome destekliyorsa ekranda "Uygulamayı yükle" butonu da görünür.

## Önemli

Bu sürümde SQLite ve kayıt dosyaları sunucu diskinde tutulur. Üretim sürümünde kalıcı depolama için Supabase/Postgres + object storage'a geçmek gerekir. Render gibi bazı platformların ücretsiz/ephemeral disk seçeneklerinde yeniden deploy sonrası yerel dosyalar korunmayabilir.

## Sonraki adım

- Supabase Auth
- Her kedi için profil
- Sesleri object storage'da kalıcı tutma
- Sesleri 16 kHz mono WAV'a normalize etme
- Audio embedding
- Kişisel sınıflandırıcı
- "Kedime Söyle" playback/deney ekranı
