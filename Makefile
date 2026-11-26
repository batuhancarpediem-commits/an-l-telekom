PY ?= python3

.PHONY: video setup audio assets music clean

# Tek komutla video üret:  make video
video:
	$(PY) src/build.py

# Yalnızca seslendirmeleri üret (video render etmeden dinleyip kontrol etmek için)
audio:
	$(PY) src/build.py --audio-only

# Marka logolarını ve ürün görsellerini resmî sitelerden indir (bulunamayanlar raporlanır; sahte görsel üretilmez)
assets:
	$(PY) src/fetch_assets.py

# Telifsiz arka plan müziğini (yeniden) üret: assets/music.mp3
music:
	$(PY) src/make_music.py

# İlk kurulum
setup:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m playwright install chromium

clean:
	rm -rf cache/work output/*.mp4
