# XNU/Apple Security Watch

7/24 (6 saatte bir tetiklenen) GitHub Actions tabanlı, 6 açık kaynak model ile
çalışan, Apple platform açık kaynak yüzeyini (XNU, dyld, Security/Gatekeeper,
WebKit, Swift runtime) tarayıp 3 katmanlı kolektif statik analiz yapan sistem.

**Kapsam:** Sadece tespit + hipotez. Exploit/PoC üretmez. Çıkış, insan
araştırmacının manuel doğrulaması için bir "lead" (ipucu) listesidir.

## Mimari

```
GitHub tarama (XNU/dyld/Security/WebKit/Swift)
        ↓
Layer 1: 6 model bağımsız analiz
        ↓
Layer 2: 6 model birbirinin çıkışını okur, itiraz/güçlendirme/sentez yapar
        ↓
Layer 3: final hipotez damıtılır, REPORTABLE/LATENT/DISCARD
        ↓
6/6 modelden ≥4'ü REPORTABLE derse → findings/findings_log.json'a kaydedilir
        ↓
10 saat REPORTABLE bulunamazsa → arşivdeki LATENT/DISCARD adaylar farklı
bir lens ile yeniden incelenir (starvation mode)
```

## Kurulum (5 dakika)

1. **Bu klasördeki tüm dosyaları GitHub'da yeni bir repo'ya yükle**
   (private repo önerilir — kendi araştırma notların).

2. **Secrets ekle** — Repo → Settings → Secrets and variables → Actions →
   "New repository secret". OpenRouter'dan (openrouter.ai) 6 ayrı API key al
   (her model kendi key'ini kullanır, tek key'in rate limitine tıkanmamak
   için) ve şu isimlerle ekle:
   - `OPENROUTER_API_KEY_1`
   - `OPENROUTER_API_KEY_2`
   - `OPENROUTER_API_KEY_3`
   - `OPENROUTER_API_KEY_4`
   - `OPENROUTER_API_KEY_5`
   - `OPENROUTER_API_KEY_6`

   `GITHUB_TOKEN` ayrıca eklemene gerek yok — GitHub Actions bunu otomatik
   sağlıyor.

   ⚠️ Key'leri asla `config.py`/`models.py` içine yazma veya chat/commit
   mesajlarına yapıştırma — sadece GitHub Secrets'a. Secrets şifrelenir ve
   workflow log'larında otomatik maskelenir; kod içine gömülen bir key ise
   git geçmişinde kalıcı olarak görünür kalır.

3. **Actions sekmesine git, workflow'u etkinleştir.** İlk çalıştırmayı
   manuel tetiklemek için: Actions → "XNU/Apple Security Watch" → "Run workflow".

4. Bundan sonra **her 6 saatte bir otomatik** çalışır (`.github/workflows/xnu-watch.yml`
   içindeki cron ifadesinden değiştirilebilir).

## Sonuçları görme

- `findings/findings_log.json` — her analiz edilen aday + 3 katmanın tam
  muhakeme zinciri + final verdict. Repo'ya otomatik commit edilir.
- `findings/archive.json` — LATENT/DISCARD adayların arşivi (starvation mode
  için).
- Actions sekmesinde her çalıştırmanın logu (`[RESULT] ... -> REPORTABLE` gibi
  satırlar) görülebilir.

## Hedefleri/modelleri değiştirme

- `config.py` → `WATCH_TARGETS`: hangi repo/path'ler izleniyor.
- `config.py` → `CONSENSUS_THRESHOLD`: kaç modelin "reportable" demesi
  gerektiği (şu an 6'dan 4).
- `models.py` → `ROSTER`: hangi 6 model kullanılıyor.
- `prompts.py` → `TARGET_LENSES`: her hedefe özel analiz açısı.

## Maliyet

Tamamen ücretsiz/açık kaynak modeller üzerinde çalışır (OpenRouter, 6 ayrı
key). Her aday için 6 model × 3 katman = 18 API çağrısı yapılır;
`MAX_CANDIDATES_PER_RUN` ile çalıştırma başına işlenen aday sayısı
sınırlanır (varsayılan: 4).
