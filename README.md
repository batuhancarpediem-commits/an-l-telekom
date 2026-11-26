# Anıl Telekomünikasyon – Kurumsal Tanıtım Filmi

Kodla üretilen, **Türkçe seslendirmeli** tanıtım filmi: 1920×1080, 30 fps, H.264 (CRF 18) + AAC 192k.

**Akış:** Giriş (logo, slogan) → 9 marka (Dahua, Ajax Systems, Ruijie, Lande, Paradox, Gigaset, Karel, Seagate, Yealink; her biri marka tanıtımı + ürün slaytları) → mağaza dış cephe → iletişim (telefon · web · adres · e-posta).

## Gerçekçilik ilkeleri (kodda uygulanır)
- **Yalnızca gerçek görsel:** logo ve ürün fotoğrafları `assets/` altından gelir. Yapay zekâ ile ürün/logo üretilmez, **yer tutucu çizilmez**. Görseli olmayan ürünün slaytı atlanır, logosu olmayan markada marka adı yazı olarak gösterilir; her ikisi de uyarı olarak raporlanır.
- **Sinematik hareket:** her fotoğrafta yavaş Ken Burns (komşu sahnelerde farklı yön); mağaza karesinde yavaş yaklaşan kamera. Titreme olmaması için kaynak 4K'ya ölçeklenip öyle işlenir.
- **Stüdyo hissi:** ürünlerin arka planı temizlenir, yumuşak gölge + hafif yansıma eklenir; çok hafif vignette ve renk düzeltmesi.
- **Geçişler:** yumuşak çapraz geçiş ve hafif kayma (`config.json > video.transitions`). Spin/3D yok.
- **Yazılar:** logo ve metinler keskin, sade (fade + hafif yukarı kayma).
- **Çözünürlük uyarısı:** düşük çözünürlüklü fotoğraf (ürün < 700 px, mağaza < 1920 px) için uyarı verilir.
- **Senkron:** her slaytın süresi seslendirmeden otomatik hesaplanır; slayt, konuşma bitmeden değişmez; geçişler cümle başlarına hizalanır.

## Ses
- **Sağlayıcı önceliği:** ElevenLabs (`eleven_multilingual_v2`, stability 0.40, style 0.35, doğal hız) → Google Cloud TTS (Chirp3-HD, yoksa Wavenet) → Edge TTS (yedek, anahtarsız). Yalnızca anahtarı tanımlı olanlar denenir; biri çalışmazsa sıradakine geçilir, hiçbiri çalışmazsa sessiz video üretmek yerine açık hata verilir.
- **Metinler** günlük konuşma dilinde: kısa cümleler, "Peki hangi markalarla çalışıyoruz?" gibi doğal bağlaçlar, virgül ve üç noktayla nefes payı.
- **Telaffuz sözlüğü:** `pronunciation.json` (`"Seagate": "sigeyt"`). Yanlış okunan her kelimeyi buraya ekleyin; ekrandaki yazı değişmez.
- **Normalizasyon:** seslendirme −16 LUFS'a normalize edilir; `config.json > audio > room_reverb: true` hafif oda sesi ekler.
- **Müzik:** `assets/music.mp3` (bu projede **sentezlenmiş, özgün, telifsiz** bir pad; `make music` ile yeniden üretilir). Konuşma sırasında otomatik kısılır (ducking). Kendi müziğinizle değiştirebilirsiniz.

## GitHub'da MP4 olarak indirme (adım adım)
1. **Depo:** github.com → **+ → New repository** → `anil-telekom-video` → **Create repository**.
2. **Dosyalar:** **uploading an existing file** → zip'i açıp içindekilerin **tamamını** (`src`, `templates`, `assets`, `content.json`, `config.json`, `pronunciation.json`, `requirements.txt`, `Makefile`, `README.md`, `.gitignore`…) sürükleyin → **Commit changes**.
3. **İş akışı:** `.github` klasörü gizli olduğu için elle ekleyin: **Add file → Create new file** → ad kutusuna `.github/workflows/build-video.yml` yazın → zip'teki aynı dosyanın içeriğini yapıştırın → **Commit changes**.
4. **Ses anahtarı (önerilir):** **Settings → Secrets and variables → Actions → New repository secret**: `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` (Voice Library'den Türkçe konuşan kadın bir ses seçin) veya `GOOGLE_TTS_API_KEY`. Hiçbiri yoksa Edge TTS kullanılır.
5. **Üretim:** **Actions → Videoyu üret → Run workflow**. Süre: marka görsellerine bağlı olarak ~15–30 dk. (Sonradan `content.json`, `assets/` vb. değiştirip commit ederseniz video kendiliğinden yeniden üretilir.)
6. **Görsel raporu:** çalışma bitince sayfanın üstündeki **Summary** bölümünde hangi logo/ürün görselinin indirildiği, hangilerinin **EKSİK** olduğu tablo olarak görünür.
7. **MP4'ü indirin:**
   - **Releases** (en kolayı): depo ana sayfası, sağ kenar → **Releases** → en üstteki sürüm → **Assets** → `anil-telekom-tanitim.mp4`.
   - veya **Actions → son çalışma → Artifacts → `anil-telekom-tanitim`** (zip iner, içinde MP4).

> "Resource not accessible by integration" hatası: **Settings → Actions → General → Workflow permissions → Read and write permissions** → Save, sonra tekrar çalıştırın.

## Görseller: otomatik + elle
`make assets` (GitHub'da otomatik çalışır) resmî sitelerden logo ve ürün görseli bulmaya çalışır: önce elle koyduğunuz dosyalar, sonra `content.json` içindeki `logo_url` / `image_url`, sonra marka sayfası (`url`) ve ürün sayfasından (`page`) otomatik keşif. Banner, yanlış oran ve çok küçük görseller elenir.

Otomatik bulunamayanlar için **gerçek** fotoğrafı doğrudan depoya koyun (GitHub'da **Add file → Upload files**):
- Logolar: `assets/brands/<marka>.png` (şeffaf PNG tercih edilir; örn. `dahua.png`, `ajax.png`, `ruijie.png`, `lande.png`, `paradox.png`, `gigaset.png`, `karel.png`, `seagate.png`, `yealink.png`)
- Ürünler: `assets/products/<ad>.jpg|png` (dosya adları `content.json > brands[].products[].image` alanındadır). En az 1500 px, temiz (beyaz/şeffaf) fonlu stüdyo fotoğrafı önerilir.
- Mağaza: `assets/office.jpg` (≥ 1920 px) veya kısa bir klip için `content.json > office.video`.

Marka/ürün görselleri ilgili markaların telif ve marka hakkı kapsamındadır; yetkili bayi olarak kullanım izninizi ve markaların kurumsal kimlik kurallarını kontrol edin.

## Metinleri değiştirme
Her şey `content.json` içindedir: ekran yazıları ve **seste okunan** `narration` alanları. Telefon, web ve e-posta okunuşları `contact.narration` içinde elle yazılıdır; bilgiyi değiştirirseniz onu da güncelleyin. Bir markayı çıkarmak için `brands` listesinden silin.

## Kendi bilgisayarınızda
```bash
make setup     # paketler + Chromium (bir kez); FFmpeg kurulu olmalı
make assets    # logo/ürün görsellerini indir + rapor (cache/asset-report.md)
make audio     # yalnızca seslendirmeleri üret, süreleri göster
make video     # output/anil-telekom-tanitim.mp4
```
Ses anahtarlarını `.env.example` dosyasını `.env` olarak kopyalayıp doldurun.

## Sorun giderme
- **"Hiçbir seslendirme sağlayıcısı çalışmadı":** Edge TTS GitHub sunucularında engellenmiş olabilir; ElevenLabs veya Google anahtarı ekleyin.
- **Çok sayıda "EKSİK / ATLANDI" uyarısı:** ilgili görselleri yukarıdaki yollara elle koyun.
- **Telaffuz hatası:** `pronunciation.json`'a ekleyin; `make audio` ile sadece sesleri yeniden üretip dinleyin (önbellek sayesinde değişmeyen metinler yeniden üretilmez).
